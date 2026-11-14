"""Fresh cure-condition and economic-loss check; 750k aggregate reserve, dry-run default."""

from run_codex_completeness8 import main

if __name__ == "__main__":
    main(cohort_ids={"dod-005", "mh-012"}, label="codex-coverage-precision2", allowance=750_000)
