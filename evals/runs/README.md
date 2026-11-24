# Saved model outputs

Raw answers and verdicts produced by the eval steps. They are committed so that every number in
`evals/results/` can be traced back to the exact output it was computed from, and so a rerun of
the scoring does not have to pay for the model calls again. Delete a file to force that step to
run afresh.
