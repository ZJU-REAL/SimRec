#!/usr/bin/env bash
# Launch a SimRec GRPO run.  All machine-specific paths belong in CONFIG_FILE.
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_dir=$(dirname "$repo_dir")
config_file=${CONFIG_FILE:-"$repo_dir/configs/train.env"}
if [[ "$config_file" != /* ]]; then
  config_file="$repo_dir/$config_file"
fi

cd "$repo_dir"

if [[ ! -f "$config_file" ]]; then
  echo "Missing config: $config_file (copy configs/train.env.example to configs/train.env)." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$config_file"
set +a

for variable in MODEL_NAME TRAIN_DATA VAL_DATA TEST_DATA SEARCH_INDEX_DIR SEARCH_MODEL_PATH; do
  if [[ -z "${!variable:-}" ]]; then
    echo "$variable must be set in $config_file" >&2
    exit 2
  fi
done

if [[ ! -f "$TRAIN_DATA" || ! -f "$VAL_DATA" || ! -f "$TEST_DATA" ]]; then
  echo "TRAIN_DATA, VAL_DATA, and TEST_DATA must point to existing JSONL files." >&2
  exit 2
fi

train_data_canonical=$(realpath "$TRAIN_DATA")
val_data_canonical=$(realpath "$VAL_DATA")
test_data_canonical=$(realpath "$TEST_DATA")
if [[ "$train_data_canonical" == "$val_data_canonical" || \
      "$train_data_canonical" == "$test_data_canonical" || \
      "$val_data_canonical" == "$test_data_canonical" ]]; then
  echo "TRAIN_DATA, VAL_DATA, and TEST_DATA must be three distinct files." >&2
  exit 2
fi

if [[ -n "${GPUS:-}" ]]; then
  export CUDA_VISIBLE_DEVICES=$GPUS
fi
gpu_list=${CUDA_VISIBLE_DEVICES:-0}
gpu_count=$(awk -F, '{print NF}' <<<"${gpu_list// /}")
export N_GPUS_PER_NODE=${N_GPUS_PER_NODE:-$gpu_count}
export VERL_REPO_ROOT=${VERL_REPO_ROOT:-"$workspace_dir/verl"}
export PYTHONPATH="$repo_dir/src:$VERL_REPO_ROOT:${PYTHONPATH:-}"

strategy=${STRATEGY:-fsdp}
use_dynamic_bsz=${USE_DYNAMIC_BSZ:-False}
do_offload=${DO_OFFLOAD:-True}
free_cache_engine=${FREE_CACHE_ENGINE:-False}
max_num_seqs=${MAX_NUM_SEQS:-64}
rollout_max_model_len=${ROLLOUT_MAX_MODEL_LEN:-$(( ${MAX_PROMPT_LENGTH:-2048} + ${MAX_RESPONSE_LENGTH:-1024} + 128 ))}
max_num_batched_tokens=${MAX_NUM_BATCHED_TOKENS:-$rollout_max_model_len}
actor_ppo_max_token_len_per_gpu=${ACTOR_PPO_MAX_TOKEN_LEN_PER_GPU:-$rollout_max_model_len}
validation_freq=${VALIDATION_FREQ:-20}
checkpoint_root=${CHECKPOINT_ROOT:-checkpoints}
run_name=${RUN_NAME:-simrec}
checkpoint_dir="$checkpoint_root/$run_name"
run_mode=${SIMREC_RUN_MODE:-train}
data_train_file=$TRAIN_DATA
data_val_file=$VAL_DATA
model_path=$MODEL_NAME
val_only=false
val_before_train=${VAL_BEFORE_TRAIN:-false}
if [[ "$run_mode" == "eval" ]]; then
  eval_data=${EVAL_DATA:-$TEST_DATA}
  if [[ ! -f "$eval_data" ]]; then
    echo "EVAL_DATA must point to an existing JSONL file." >&2
    exit 2
  fi
  # verl constructs a train dataset even for val_only; use validation data for
  # that inert input and reserve EVAL_DATA exclusively for validation rollout.
  data_train_file=$VAL_DATA
  data_val_file=$eval_data
  model_path=${EVAL_MODEL_PATH:-$MODEL_NAME}
  export SIMREC_VALIDATION_INJECT_TARGET_ON_MISS=false
  val_only=true
  val_before_train=true
elif [[ "$run_mode" != "train" ]]; then
  echo "SIMREC_RUN_MODE must be train or eval." >&2
  exit 2
fi
mkdir -p "$checkpoint_dir"
ray_overrides=()
if [[ -n ${RAY_TMP_DIR:-} ]]; then
  mkdir -p "$RAY_TMP_DIR"
  ray_overrides+=("+ray_kwargs.ray_init._temp_dir=$RAY_TMP_DIR")
fi
if [[ -n ${RAY_INCLUDE_DASHBOARD:-} ]]; then
  ray_overrides+=("+ray_kwargs.ray_init.include_dashboard=$RAY_INCLUDE_DASHBOARD")
fi

if [[ -n ${USE_KL_LOSS:-} ]]; then
  use_kl_loss=$USE_KL_LOSS
else
  use_kl_loss=$(awk "BEGIN {print ((${KL_LOSS_COEF:-0.0} + 0) > 0) ? \"True\" : \"False\"}")
fi

if [[ "$run_mode" == "eval" ]]; then
  echo "Evaluation policy: model=$model_path | validation-only dataset=$data_val_file"
else
  echo "Split policy: train=$TRAIN_DATA | validation=$VAL_DATA | held-out test=$TEST_DATA"
  echo "Checkpoint and validation frequency: every ${SAVE_FREQ:-20} / ${validation_freq} steps"
fi

mode=${SIMREC_USER_SIMULATOR_MODE:-external}
case "$mode" in
  self_play|self-play|selfplay)
    dataset_path=src/SimRec/self_play/dataset.py
    reward_path=src/SimRec/self_play/reward_manager.py
    tool_config=${TOOL_CONFIG_FILE:-"$repo_dir/configs/tool_config/self_play_tools.yaml"}
    interaction_config=${INTERACTION_CONFIG_FILE:-"$repo_dir/configs/interaction_config/self_play_user.yaml"}
    agent_loop=simrec_self_play_tool_agent
    ;;
  external|api|llm)
    dataset_path=src/SimRec/dataset.py
    reward_path=src/SimRec/reward_manager.py
    tool_config=${TOOL_CONFIG_FILE:-"$repo_dir/configs/tool_config/external_tools.yaml"}
    interaction_config=${INTERACTION_CONFIG_FILE:-"$repo_dir/configs/interaction_config/external_user.yaml"}
    agent_loop=simrec_tool_agent
    ;;
  *)
    echo "SIMREC_USER_SIMULATOR_MODE must be external or self_play." >&2
    exit 2
    ;;
esac

python_bin=${PYTHON_BIN:-python3}
"$python_bin" -m SimRec.main_ppo \
  algorithm.adv_estimator=${RL_ALG:-grpo} \
  data.train_files="$data_train_file" data.val_files="$data_val_file" \
  data.seed=${SEED:-42} \
  data.train_batch_size=${TRAIN_BATCH_SIZE:-8} data.val_batch_size=${VAL_BATCH_SIZE:-4} \
  data.max_prompt_length=${MAX_PROMPT_LENGTH:-2048} data.max_response_length=${MAX_RESPONSE_LENGTH:-1024} \
  data.custom_cls.path="$dataset_path" data.custom_cls.name=SimRecDataset \
  reward.reward_manager.source=importlib reward.reward_manager.name=SimRecRewardManager \
  reward.reward_manager.module.path="$reward_path" reward.reward_manager.module.name=SimRecRewardManager \
  actor_rollout_ref.model.path="$model_path" critic.model.path="$model_path" \
  actor_rollout_ref.model.enable_gradient_checkpointing=True \
  actor_rollout_ref.model.use_remove_padding=True \
  actor_rollout_ref.model.trust_remote_code=True \
  actor_rollout_ref.actor.optim.lr=${LR:-5e-7} critic.optim.lr=${CRITIC_LR:-5e-6} \
  algorithm.kl_ctrl.kl_coef=${KL_COEF:-0.001} \
  actor_rollout_ref.actor.clip_ratio_low=${CLIP_RATIO:-0.2} \
  actor_rollout_ref.actor.clip_ratio_high=${CLIP_RATIO:-0.2} \
  actor_rollout_ref.actor.ppo_mini_batch_size=${PPO_MINI_BATCH_SIZE:-4} \
  actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=${PPO_MICRO_BATCH_SIZE_PER_GPU:-1} \
  actor_rollout_ref.actor.use_dynamic_bsz=$use_dynamic_bsz \
  actor_rollout_ref.actor.use_kl_loss=$use_kl_loss \
  actor_rollout_ref.actor.kl_loss_coef=${KL_LOSS_COEF:-0.0} \
  actor_rollout_ref.actor.kl_loss_type=${KL_LOSS_TYPE:-low_var_kl} \
  actor_rollout_ref.actor.entropy_coeff=${ENTROPY_COEFF:-0.0} \
  actor_rollout_ref.actor.strategy=$strategy \
  actor_rollout_ref.actor.fsdp_config.param_offload=$do_offload \
  actor_rollout_ref.actor.fsdp_config.optimizer_offload=$do_offload \
  actor_rollout_ref.actor.ppo_max_token_len_per_gpu=$actor_ppo_max_token_len_per_gpu \
  critic.ppo_micro_batch_size_per_gpu=${PPO_MICRO_BATCH_SIZE_PER_GPU:-1} \
  actor_rollout_ref.rollout.name=vllm actor_rollout_ref.rollout.n=${ROLLOUT_N:-8} \
  actor_rollout_ref.rollout.mode=${ROLLOUT_MODE:-async} \
  actor_rollout_ref.rollout.tensor_model_parallel_size=${TENSOR_MODEL_PARALLEL_SIZE:-1} \
  actor_rollout_ref.rollout.temperature=${TEMPERATURE:-1.0} \
  actor_rollout_ref.rollout.top_p=${TOP_P:-1.0} \
  actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=${LOGPROB_MICRO_BATCH_SIZE_PER_GPU:-1} \
  actor_rollout_ref.rollout.log_prob_use_dynamic_bsz=$use_dynamic_bsz \
  actor_rollout_ref.rollout.gpu_memory_utilization=${GPU_MEMORY_UTILIZATION:-0.4} \
  actor_rollout_ref.rollout.max_model_len=$rollout_max_model_len \
  actor_rollout_ref.rollout.max_num_batched_tokens=$max_num_batched_tokens \
  actor_rollout_ref.rollout.max_num_seqs=$max_num_seqs \
  actor_rollout_ref.rollout.free_cache_engine=$free_cache_engine \
  actor_rollout_ref.rollout.enable_chunked_prefill=${ENABLE_CHUNKED_PREFILL:-False} \
  actor_rollout_ref.rollout.multi_turn.enable=True \
  actor_rollout_ref.rollout.multi_turn.format=${TOOL_CALL_FORMAT:-hermes} \
  actor_rollout_ref.rollout.multi_turn.max_assistant_turns=${MAX_TURNS:-4} \
  actor_rollout_ref.rollout.multi_turn.tool_config_path="$tool_config" \
  actor_rollout_ref.rollout.multi_turn.interaction_config_path="$interaction_config" \
  actor_rollout_ref.rollout.agent.default_agent_loop="$agent_loop" \
  actor_rollout_ref.rollout.agent.num_workers=${AGENT_NUM_WORKERS:-1} \
  trainer.project_name=SimRec trainer.experiment_name=${RUN_NAME:-simrec} \
  trainer.n_gpus_per_node="$N_GPUS_PER_NODE" trainer.nnodes=${N_NODES:-1} \
  trainer.default_local_dir="$checkpoint_dir" \
  trainer.resume_mode=${TRAINER_RESUME_MODE:-auto} \
  trainer.resume_from_path=${TRAINER_RESUME_FROM_PATH:-null} \
  trainer.val_before_train=$val_before_train trainer.val_only=$val_only \
  trainer.total_epochs=${TOTAL_EPOCHS:-1} \
  trainer.total_training_steps=${TOTAL_TRAINING_STEPS:-200} \
  trainer.save_freq=${SAVE_FREQ:-20} trainer.test_freq=$validation_freq \
  trainer.logger="['console']" \
  "${ray_overrides[@]}" \
  ${HYDRA_EXTRA_OVERRIDES:-}
