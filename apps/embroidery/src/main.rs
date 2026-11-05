//! Entry point: parse the CLI, load config, start telemetry, dispatch, map errors to an exit code.
//!
//! CronJobs and Jobs read the exit code to decide whether a run failed, which is why errors become
//! `ExitCode::FAILURE` instead of `main` returning a `Result`.

use std::process::ExitCode;

use clap::Parser as _;
use embroidery::{cli, config::Config, telemetry};

fn main() -> ExitCode {
    let cli = cli::Cli::parse();
    let config = match Config::load() {
        Ok(config) => config,
        Err(err) => {
            #[expect(clippy::print_stderr, reason = "telemetry needs the config to start")]
            {
                eprintln!("invalid configuration: {err}");
            }
            return ExitCode::FAILURE;
        }
    };
    telemetry::init(&config.logging);

    let runtime = match tokio::runtime::Runtime::new() {
        Ok(runtime) => runtime,
        Err(err) => {
            tracing::error!(error = %err, "failed to start the Tokio runtime");
            return ExitCode::FAILURE;
        }
    };
    match runtime.block_on(cli::dispatch(cli, config)) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            tracing::error!(error = ?err, "command failed");
            ExitCode::FAILURE
        }
    }
}
