"""python -m scripts.train_model  -> trains the local triage model on synthetic data."""
import json
from app import config
from app.services import ml

if __name__ == "__main__":
    print(json.dumps(ml.train(config.MODEL_DIR), indent=2))
