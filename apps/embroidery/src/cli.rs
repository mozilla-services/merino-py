//! Command-line interface. Every Deployment, CronJob and Job runs the same binary with a
//! different subcommand.

use clap::{Parser, Subcommand};

use crate::config::Config;

#[derive(Debug, Parser)]
#[command(
    version,
    about = "Embroidery, Mozilla's image service for Firefox favicons and logos"
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    /// Run the HTTP API.
    Serve,
}

/// Runs the selected command to completion.
///
/// # Errors
///
/// Returns the command's error, which `main` logs and maps it to a failing exit code.
pub async fn dispatch(cli: Cli, config: Config) -> anyhow::Result<()> {
    match cli.command {
        Command::Serve => crate::run_server(config).await,
    }
}

#[cfg(test)]
mod tests {
    use clap::CommandFactory as _;

    use super::Cli;

    #[test]
    fn cli_definition_is_valid() {
        Cli::command().debug_assert();
    }
}
