# SugarWOD Workout Exports

This folder is the drop location for manually exported SugarWOD workout data.

## Where to Export From
Export your workout history from:
https://app.sugarwod.com/athletes/me#profile

(Use the SugarWOD UI export feature.)

## File Naming Convention
Save exports using the following format:

workouts_YYYYMMDD.csv

Example:
- workouts_20260107.csv

This allows scripts to automatically detect the most recent export.

## How to Process the Export

From the repository root, run:

1. Import and normalize the SugarWOD CSV:
```bash
python3 scripts/import_sugarwod_csv.py


2. Generate fitness metrics for the target year:
python3 scripts/fitness_metrics.py

