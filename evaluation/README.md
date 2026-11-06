# Evaluation

[`evaluate_simrec.sh`](evaluate_simrec.sh) is the public held-out evaluation
entry point. It delegates shared configuration parsing to the training launcher
while enabling `SIMREC_RUN_MODE=eval`, so no optimizer update is performed.

See [docs/EVALUATION.md](../docs/EVALUATION.md) for the split discipline,
checkpoint requirement, and metric protocol.
