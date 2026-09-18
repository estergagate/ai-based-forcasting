# Forecasting research notes

## Dataset
Public external data: MEVGAL Dairy Supply Chain Sales Dataset,
Product 1, 2020–2022.
Source: https://zenodo.org/records/7853252

The data is not synthetic and is not from our participating businesses.
Target: daily quantity sold, not peso revenue.

## Preparation
1,092 original dated records.
Four missing calendar dates and four negative quantities were flagged.
Flagged target values were excluded, not converted to zero.
Calendar dates were preserved.
The meaning of negative quantities remains unconfirmed.

## Evaluation design
Initial training: 2020, after a 28-day history period.
Validation: 2021.
Two Random Forest settings were compared using validation MAE.
Selected settings: 200 trees, max_depth=12, min_samples_leaf=3,
random_state=42.
Final evaluated model refitted on eligible 2020–2021 records.

Test period: 2022.
Rolling one-day-ahead evaluation uses actual prior-day history.
This is not a seven-day-ahead or full-year-ahead evaluation.

Both methods were compared on 362 eligible dates; three were skipped.
Missing historical inputs were imputed using training-set medians.

## Results
Seven-day seasonal naive baseline:
- MAE: 790.34 units
- RMSE: 1,076.27 units

Random Forest:
- MAE: 638.94 units
- RMSE: 867.86 units

Approximate error reduction:
- MAE: 19.2%
- RMSE: 19.4%

These are error reductions, not accuracy percentages.

## Limits
Results apply to this external product and evaluation period.
They do not establish forecasting accuracy for Philippine bakeries,
carinderias, or food stalls.
Do not repeatedly tune settings using the 2022 test results.
The website must label these results as external dataset evaluation.

## Evidence files
data/results/dairy_product_1_metrics.json
data/results/dairy_product_1_model_comparison.csv
models/dairy_product_1_random_forest.joblib