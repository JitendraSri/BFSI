# Model artifacts

Trained Transaction Intelligence models and their metrics live here. They are produced by retraining (`python app.py --seed`, the Training Lab on the Predictive page, or `POST /api/retrain`) and read back at startup.

| File | What it is |
|---|---|
| `fraud_model.pkl` | Supervised **Random Forest** fraud classifier (200 trees, depth 10, `balanced_subsample`) |
| `anomaly_model.pkl` | Unsupervised **Isolation Forest**, trained only on non-fraud rows |
| `encoder.pkl` | Fitted preprocessing / channel encoder shared by both detectors |
| `metrics.json` | Latest measured metrics (ROC-AUC, PR-AUC, fraud-class precision/recall/F1, false-positive rate, detection latency, confusion matrix, learned alert threshold) — surfaced live on the Insights page |
| `metrics_history.json` | Rolling snapshot of the last 50 retrains, powering the model-drift chart |

These `.pkl` files are small (scikit-learn models over a few numeric features) and are regenerated on retrain, so they can be kept out of source control if preferred. The hybrid risk score is `0.75 × Random Forest probability + 0.25 × anomaly score`; see the main [README](../../README.md#transaction-intelligence-engine) for the full pipeline and measured results.
