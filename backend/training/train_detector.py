"""
train_detector.py — Train a YOLO card detector using Roboflow datasets.

This script:
  1. Downloads a Pokémon card detection dataset from Roboflow Universe
  2. Trains a YOLOv8 model to detect cards in photos
  3. Exports the trained model for use in the scan pipeline

The trained model is saved to backend/models/card_detector.pt and is
automatically picked up by card_detector.py when CARD_DETECTOR_MODE=local.

Prerequisites:
    pip install ultralytics roboflow

Usage:
    # Train with default Roboflow dataset (requires ROBOFLOW_API_KEY)
    python train_detector.py

    # Train with a specific dataset
    python train_detector.py --workspace pokemon-scanner --project pokemon-card-detector-cuyon --version 1

    # Quick test with fewer epochs
    python train_detector.py --epochs 10

    # Resume training from a checkpoint
    python train_detector.py --resume
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")


def setup_roboflow_dataset(workspace: str, project: str, version: int,
                           api_key: str, format: str = "yolov8") -> str:
    """
    Download a dataset from Roboflow Universe.
    Returns the path to the dataset directory.
    """
    from roboflow import Roboflow

    rf = Roboflow(api_key=api_key)
    proj = rf.workspace(workspace).project(project)
    dataset = proj.version(version).download(format)

    print(f"Dataset downloaded to: {dataset.location}")
    return dataset.location


def train_yolo(dataset_path: str, epochs: int = 50, img_size: int = 640,
               batch: int = 16, model_size: str = "n", resume: bool = False) -> str:
    """
    Train a YOLOv8 model on the downloaded dataset.
    Returns path to the best weights file.
    """
    from ultralytics import YOLO

    # Use a pretrained YOLOv8 model as starting point
    model_name = f"yolov8{model_size}.pt"
    model = YOLO(model_name)

    # Find the data.yaml in the dataset
    data_yaml = Path(dataset_path) / "data.yaml"
    if not data_yaml.exists():
        # Try common alternative paths
        for candidate in [
            Path(dataset_path) / "dataset.yaml",
            Path(dataset_path) / "config.yaml",
        ]:
            if candidate.exists():
                data_yaml = candidate
                break

    if not data_yaml.exists():
        print(f"ERROR: Could not find data.yaml in {dataset_path}")
        print("Available files:", list(Path(dataset_path).rglob("*.yaml")))
        sys.exit(1)

    print(f"\nTraining YOLOv8{model_size} on {data_yaml}")
    print(f"  Epochs: {epochs}")
    print(f"  Image size: {img_size}")
    print(f"  Batch size: {batch}")

    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=img_size,
        batch=batch,
        name="pokemon_card_detector",
        project=str(BACKEND_DIR / "runs"),
        exist_ok=True,
        resume=resume,
        # Augmentation settings tuned for card photos
        hsv_h=0.015,    # slight hue variation (lighting differences)
        hsv_s=0.4,      # saturation variation
        hsv_v=0.3,      # brightness variation
        degrees=15.0,    # rotation (tilted cards)
        translate=0.1,   # translation
        scale=0.3,       # scale variation
        flipud=0.0,      # no vertical flip (cards don't flip)
        fliplr=0.0,      # no horizontal flip (text would be mirrored)
        mosaic=0.5,      # mosaic augmentation (multiple cards)
        mixup=0.0,       # no mixup (would confuse card identity)
    )

    # Find best weights
    best_weights = BACKEND_DIR / "runs" / "pokemon_card_detector" / "weights" / "best.pt"
    if not best_weights.exists():
        print(f"WARNING: best.pt not found at {best_weights}")
        # Try to find it
        found = list((BACKEND_DIR / "runs").rglob("best.pt"))
        if found:
            best_weights = found[0]
        else:
            print("ERROR: No trained weights found!")
            sys.exit(1)

    return str(best_weights)


def export_model(weights_path: str) -> None:
    """Copy the trained model to the expected location."""
    output_dir = BACKEND_DIR / "models"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "card_detector.pt"

    shutil.copy2(weights_path, output_path)
    print(f"\nModel exported to: {output_path}")
    print("The card_detector.py module will now use this model when CARD_DETECTOR_MODE=local")


def main():
    parser = argparse.ArgumentParser(
        description="Train a YOLO card detector using Roboflow datasets"
    )
    parser.add_argument("--workspace", default="pokemon-scanner",
                        help="Roboflow workspace name")
    parser.add_argument("--project", default="pokemon-card-detector-cuyon",
                        help="Roboflow project name")
    parser.add_argument("--version", type=int, default=1,
                        help="Dataset version number")
    parser.add_argument("--epochs", type=int, default=50,
                        help="Number of training epochs")
    parser.add_argument("--img-size", type=int, default=640,
                        help="Training image size")
    parser.add_argument("--batch", type=int, default=16,
                        help="Batch size")
    parser.add_argument("--model-size", choices=["n", "s", "m", "l", "x"],
                        default="s",
                        help="YOLO model size (n=nano, s=small, m=medium, l=large, x=xlarge)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume training from last checkpoint")
    parser.add_argument("--dataset-path", default=None,
                        help="Path to an already-downloaded dataset (skip Roboflow download)")
    args = parser.parse_args()

    api_key = os.getenv("ROBOFLOW_API_KEY", "")

    # Step 1: Get dataset
    if args.dataset_path:
        dataset_path = args.dataset_path
        print(f"Using existing dataset at: {dataset_path}")
    else:
        if not api_key:
            print("ERROR: ROBOFLOW_API_KEY environment variable is required.")
            print("Get a free API key at https://app.roboflow.com/settings/api-key")
            print("\nAlternatively, download a dataset manually and use --dataset-path")
            sys.exit(1)

        print("Step 1: Downloading dataset from Roboflow...")
        dataset_path = setup_roboflow_dataset(
            workspace=args.workspace,
            project=args.project,
            version=args.version,
            api_key=api_key,
        )

    # Step 2: Train
    print("\nStep 2: Training YOLO model...")
    weights_path = train_yolo(
        dataset_path=dataset_path,
        epochs=args.epochs,
        img_size=args.img_size,
        batch=args.batch,
        model_size=args.model_size,
        resume=args.resume,
    )

    # Step 3: Export
    print("\nStep 3: Exporting trained model...")
    export_model(weights_path)

    print("\n--- Training complete! ---")
    print("To use the local detector, set: CARD_DETECTOR_MODE=local")
    print("Or keep using Roboflow hosted inference: CARD_DETECTOR_MODE=roboflow")


if __name__ == "__main__":
    main()
