import shutil
from os.path import isdir
from typing import Callable, Optional

import pytest

from sample_factory.algo.utils.misc import ExperimentStatus
from sample_factory.train import make_runner
from sample_factory.utils.typing import Config
from sample_factory.utils.utils import log
from sf_examples.mujoco.mujoco_utils import mujoco_available
from sf_examples.mujoco.train_mujoco import parse_mujoco_cfg, register_mujoco_components
from tests.utils import clean_test_dir


@pytest.mark.skipif(not mujoco_available(), reason="mujoco not installed or not available on this machine")
class TestMujoco:
    @pytest.fixture(scope="class", autouse=True)
    def register_mujoco_fixture(self):
        register_mujoco_components()

    @staticmethod
    def _run_test_env(
        env: str = "mujoco_ant",
        num_workers: int = 8,
        train_steps: int = 128,
        batched_sampling: bool = False,
        serial_mode: bool = True,
        async_rl: bool = False,
        batch_size: int = 64,
        rollout: int = 8,
        expected_max_policy_lag: int = 100,
        customize_cfg_func: Optional[Callable[[Config], None]] = None,
    ):
        log.debug(f"Testing with parameters {locals()}...")
        assert train_steps > batch_size, "We need sufficient number of steps to accumulate at least one batch"

        experiment_name = "test_" + env

        cfg = parse_mujoco_cfg(argv=["--algo=APPO", f"--env={env}", f"--experiment={experiment_name}"])
        cfg.serial_mode = serial_mode
        cfg.async_rl = async_rl
        cfg.batched_sampling = batched_sampling
        cfg.num_workers = num_workers
        cfg.num_envs_per_worker = 4
        cfg.train_for_env_steps = train_steps
        cfg.batch_size = batch_size
        cfg.rollout = rollout
        cfg.decorrelate_envs_on_one_worker = False
        cfg.decorrelate_experience_max_seconds = 0
        cfg.seed = 0
        cfg.device = "cpu"

        if customize_cfg_func is not None:
            customize_cfg_func(cfg)

        directory = clean_test_dir(cfg)
        cfg, runner = make_runner(cfg)
        status = runner.init()
        if status == ExperimentStatus.SUCCESS:
            status = runner.run()
        assert status == ExperimentStatus.SUCCESS
        for key in ["version_diff_min", "version_diff_max", "version_diff_avg"]:
            assert runner.policy_lag[0][key] <= expected_max_policy_lag
        assert isdir(directory)
        shutil.rmtree(directory, ignore_errors=True)

    @pytest.mark.parametrize(
        "env_name",
        [
            "mujoco_ant",
            "mujoco_halfcheetah",
            "mujoco_humanoid",
            "mujoco_hopper",
            "mujoco_reacher",
            "mujoco_walker",
            "mujoco_swimmer",
        ],
    )
    @pytest.mark.parametrize("num_workers", [1, 8])
    @pytest.mark.parametrize("batched_sampling", [False, True])
    def test_basic_envs(self, env_name, batched_sampling, num_workers):
        self._run_test_env(env=env_name, num_workers=num_workers, batched_sampling=batched_sampling)

    @pytest.mark.parametrize("env_name", ["mujoco_pendulum", "mujoco_doublependulum"])
    @pytest.mark.parametrize("num_workers", [1, 8])
    def test_single_action_envs_batched(self, env_name, num_workers):
        """These envs only have a single action and might cause unique problems with 0-D vs 1-D tensors."""
        self._run_test_env(env=env_name, num_workers=num_workers, batched_sampling=True)

    @pytest.mark.parametrize("env_name", ["mujoco_pendulum", "mujoco_doublependulum"])
    @pytest.mark.parametrize("num_workers", [1, 8])
    def test_single_action_envs_non_batched(self, env_name, num_workers):
        """These envs only have a single action and might cause unique problems with 0-D vs 1-D tensors."""
        self._run_test_env(env=env_name, num_workers=num_workers, batched_sampling=False)

    @pytest.mark.parametrize("batched_sampling", [False, True])
    def test_synchronous_rl_zero_lag(self, batched_sampling: bool):
        def no_lag_cfg(cfg: Config):
            cfg.num_epochs = cfg.num_batches_per_epoch = 1

        self._run_test_env(
            env="mujoco_ant",
            num_workers=8,
            train_steps=1024,
            batch_size=512,
            batched_sampling=batched_sampling,
            serial_mode=False,
            async_rl=False,
            expected_max_policy_lag=0,
            customize_cfg_func=no_lag_cfg,
        )
