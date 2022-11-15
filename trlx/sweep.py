# Usage: python train_sweep.py --config configs/ray_tune_configs/ppo_config.yml --example-name ppo_sentiments
import wandb
import argparse
from pathlib import Path

import ray
from ray.air import session
from ray import tune
import importlib

import trlx
from trlx.ray_tune import load_ray_yaml
from trlx.ray_tune import get_param_space
from trlx.ray_tune import get_tune_config
from trlx.ray_tune.wandb import log_trials, create_report

from ray.tune.logger import JsonLoggerCallback
from ray.tune.logger import CSVLoggerCallback


def tune_function(
    train_function, param_space: dict, tune_config: dict, resources: dict
):
    tuner = tune.Tuner(
        tune.with_resources(train_function, resources=resources),
        param_space=param_space,
        tune_config=tune.TuneConfig(**tune_config),
        run_config=ray.air.RunConfig(
            local_dir="ray_results", callbacks=[CSVLoggerCallback()]
        ),
    )

    results = tuner.fit()
    projectname = "sweep"

    log_trials(
        tuner._local_tuner.get_experiment_checkpoint_dir(),
        projectname,
    )

    create_report(
        projectname,
        param_space,
        tune_config,
        Path(tuner._local_tuner.get_experiment_checkpoint_dir()).stem,
        results.get_best_result().config,
    )

    print("Best hyperparameters found were: ", results.get_best_result().config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script", type=str, help="Path to the script")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="The config file defining the param_space.",
    )
    parser.add_argument(
        "--num-cpus", type=int, default=4, help="Number of CPUs to use per exp."
    )
    parser.add_argument(
        "--num-gpus", type=int, default=1, help="Number of GPUs to use per exp."
    )
    parser.add_argument(
        "--server-address",
        type=str,
        default=None,
        required=False,
        help="The address of server to connect to if using Ray Client.",
    )

    args = parser.parse_args()

    # Read config and parse it
    config = load_ray_yaml(args.config)
    tune_config = get_tune_config(config.pop("tune_config"))
    param_space = get_param_space(config)

    # Initialize Ray.
    if args.server_address:
        ray.init(address=f"ray://{args.server_address}")
    else:
        ray.init()

    resources = {
        "cpu": args.num_cpus,
        "gpu": args.num_gpus,
    }

    # convert nested path to a script to a module path
    script_path = args.script.replace(".py", "").replace("/", ".")
    script = importlib.import_module(script_path)
    # Register the training function that will be used for training the model.
    tune.register_trainable("train_function", script.main)
    tune_function(script.main, param_space, tune_config, resources)

    # Shut down Ray.
    ray.shutdown()