//! Typed configuration, layered the same way as Merino and Fleece (`docs/operations/configs.md`).
//!
//! Sources, later ones overriding earlier ones:
//!
//! 1. `configs/default.toml`, embedded in the binary.
//! 2. `configs/${EMBROIDERY_ENV}.toml`, embedded in the binary.
//! 3. `configs/${EMBROIDERY_ENV}.local.toml`, read from disk if present (gitignored).
//! 4. `EMBROIDERY_SECTION__KEY` environment variables.
//!
//! Embedding the TOML files keeps the image identical across environments: a deployment only sets
//! environment variables.

use std::time::Duration;
use std::{collections::HashMap, fmt, net::IpAddr, path::Path, str::FromStr};

use config::{File, FileFormat};
use serde::{Deserialize, Deserializer};
use tracing_subscriber::EnvFilter;

const ENV_PREFIX: &str = "EMBROIDERY";
const ENV_VAR: &str = "EMBROIDERY_ENV";
const LOCAL_CONFIG_DIR: &str = "configs";

/// Service configuration, validated at startup.
///
/// Unknown top-level keys are ignored on purpose: Kubernetes injects service links such as
/// `EMBROIDERY_SERVICE_HOST` and `EMBROIDERY_PORT` into every pod in the namespace, and
/// those map to top-level keys. The sections reject unknown keys, so a typo such as
/// `EMBROIDERY_SERVER__PROT` fails at startup instead of being silently ignored.
#[derive(Debug, Deserialize)]
pub struct Config {
    /// Selected by `EMBROIDERY_ENV` only; the TOML files can't change it.
    pub env: Environment,
    pub server: ServerConfig,
    pub logging: LoggingConfig,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ServerConfig {
    pub host: IpAddr,
    pub port: u16,
    /// Maximum time a request may take before the server responds with 503.
    #[serde(
        rename = "request_timeout_secs",
        deserialize_with = "duration_from_secs"
    )]
    pub request_timeout: Duration,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LoggingConfig {
    pub format: LogFormat,
    /// An `EnvFilter` directive. Validated by [`Config::load`].
    pub level: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogFormat {
    /// JSON in Mozilla's MozLog format, for the log pipeline.
    Mozlog,
    /// Human-readable lines, for local work.
    Pretty,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Environment {
    Development,
    Testing,
    Stage,
    Production,
}

impl Environment {
    const ALL: [Self; 4] = [
        Self::Development,
        Self::Testing,
        Self::Stage,
        Self::Production,
    ];

    fn as_str(self) -> &'static str {
        match self {
            Self::Development => "development",
            Self::Testing => "testing",
            Self::Stage => "stage",
            Self::Production => "production",
        }
    }

    fn embedded_config(self) -> &'static str {
        match self {
            Self::Development => include_str!("../configs/development.toml"),
            Self::Testing => include_str!("../configs/testing.toml"),
            Self::Stage => include_str!("../configs/stage.toml"),
            Self::Production => include_str!("../configs/production.toml"),
        }
    }
}

impl fmt::Display for Environment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Environment {
    type Err = ConfigError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::ALL
            .into_iter()
            .find(|env| env.as_str() == s)
            .ok_or_else(|| ConfigError::UnknownEnvironment(s.to_owned()))
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error(
        "{ENV_VAR}={0:?} is not a known environment, expected one of: development, testing, stage, production"
    )]
    UnknownEnvironment(String),
    #[error(transparent)]
    Load(#[from] config::ConfigError),
    #[error("{key}: {reason}")]
    Invalid { key: &'static str, reason: String },
}

impl Config {
    /// Loads the configuration from the process environment and `configs/` in the working
    /// directory.
    ///
    /// # Errors
    ///
    /// Fails if `EMBROIDERY_ENV` is unknown, a source doesn't parse, a key has the wrong type
    /// or an unknown name within a section, or a value is invalid. The message includes the key.
    pub fn load() -> Result<Self, ConfigError> {
        Self::load_from(std::env::vars().collect(), Path::new(LOCAL_CONFIG_DIR))
    }

    /// Loads the configuration from explicit environment variables and local config directory.
    /// Tests use this, since mutating the process environment is `unsafe` in edition 2024.
    fn load_from(vars: HashMap<String, String>, local_dir: &Path) -> Result<Self, ConfigError> {
        let env = match vars.get(ENV_VAR) {
            Some(value) => value.parse()?,
            None => Environment::Development,
        };

        let config: Self = config::Config::builder()
            .add_source(File::from_str(
                include_str!("../configs/default.toml"),
                FileFormat::Toml,
            ))
            .add_source(File::from_str(env.embedded_config(), FileFormat::Toml))
            .add_source(
                File::from(local_dir.join(format!("{env}.local.toml")))
                    .format(FileFormat::Toml)
                    .required(false),
            )
            .add_source(
                config::Environment::with_prefix(ENV_PREFIX)
                    .prefix_separator("_")
                    .separator("__")
                    .try_parsing(true)
                    .source(Some(vars)),
            )
            .set_override("env", env.as_str())?
            .build()?
            .try_deserialize()?;

        config.validate()?;
        Ok(config)
    }

    fn validate(&self) -> Result<(), ConfigError> {
        if self.server.request_timeout.is_zero() {
            return Err(ConfigError::Invalid {
                key: "server.request_timeout_secs",
                reason: "must be greater than 0".to_owned(),
            });
        }
        if let Err(err) = EnvFilter::try_new(&self.logging.level) {
            return Err(ConfigError::Invalid {
                key: "logging.level",
                reason: format!("invalid filter directive {:?}: {err}", self.logging.level),
            });
        }
        Ok(())
    }
}

fn duration_from_secs<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Duration, D::Error> {
    u64::deserialize(deserializer).map(Duration::from_secs)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A directory without local overrides.
    const NO_LOCAL: &str = "/nonexistent";

    fn load(vars: &[(&str, &str)], local_dir: impl AsRef<Path>) -> Result<Config, ConfigError> {
        let vars = vars
            .iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect();
        Config::load_from(vars, local_dir.as_ref())
    }

    #[test]
    fn defaults_load() {
        let config = load(&[("EMBROIDERY_ENV", "production")], NO_LOCAL).unwrap();

        assert_eq!(config.env, Environment::Production);
        assert_eq!(config.server.host, IpAddr::from([0, 0, 0, 0]));
        assert_eq!(config.server.port, 8000);
        assert_eq!(config.server.request_timeout, Duration::from_secs(10));
        assert_eq!(config.logging.format, LogFormat::Mozlog);
    }

    #[test]
    fn env_defaults_to_development() {
        let config = load(&[], NO_LOCAL).unwrap();

        assert_eq!(config.env, Environment::Development);
    }

    #[test]
    fn environment_file_overrides_default() {
        let config = load(&[("EMBROIDERY_ENV", "development")], NO_LOCAL).unwrap();

        assert_eq!(config.logging.format, LogFormat::Pretty);
        assert_eq!(config.server.host, IpAddr::from([127, 0, 0, 1]));
    }

    #[test]
    fn env_var_overrides_environment_file() {
        let config = load(
            &[
                ("EMBROIDERY_ENV", "development"),
                ("EMBROIDERY_LOGGING__FORMAT", "mozlog"),
                ("EMBROIDERY_SERVER__PORT", "9000"),
            ],
            NO_LOCAL,
        )
        .unwrap();

        assert_eq!(config.logging.format, LogFormat::Mozlog);
        assert_eq!(config.server.port, 9000);
    }

    #[test]
    fn local_file_overrides_environment_file_and_env_var_overrides_both() {
        let local_dir = tempfile::tempdir().unwrap();
        std::fs::write(
            local_dir.path().join("testing.local.toml"),
            "[server]\nport = 9100\n\n[logging]\nlevel = \"debug\"\n",
        )
        .unwrap();

        let config = load(
            &[
                ("EMBROIDERY_ENV", "testing"),
                ("EMBROIDERY_LOGGING__LEVEL", "warn"),
            ],
            local_dir.path(),
        )
        .unwrap();

        assert_eq!(config.server.port, 9100);
        assert_eq!(config.logging.level, "warn");
    }

    #[test]
    fn unknown_environment_fails_with_value() {
        let err = load(&[("EMBROIDERY_ENV", "staging")], NO_LOCAL).unwrap_err();

        assert!(matches!(err, ConfigError::UnknownEnvironment(_)));
        assert!(err.to_string().contains("\"staging\""), "{err}");
    }

    #[test]
    fn unknown_section_key_fails() {
        let err = load(&[("EMBROIDERY_SERVER__PROT", "9000")], NO_LOCAL).unwrap_err();

        assert!(err.to_string().contains("prot"), "{err}");
    }

    #[test]
    fn kubernetes_service_links_are_ignored() {
        let config = load(
            &[
                ("EMBROIDERY_PORT", "tcp://10.0.0.1:8000"),
                ("EMBROIDERY_SERVICE_HOST", "10.0.0.1"),
            ],
            NO_LOCAL,
        )
        .unwrap();

        assert_eq!(config.server.port, 8000);
    }

    #[test]
    fn wrong_type_fails_with_key() {
        let err = load(&[("EMBROIDERY_SERVER__PORT", "eighty")], NO_LOCAL).unwrap_err();

        assert!(err.to_string().contains("port"), "{err}");
    }

    #[test]
    fn zero_request_timeout_fails() {
        let err = load(
            &[("EMBROIDERY_SERVER__REQUEST_TIMEOUT_SECS", "0")],
            NO_LOCAL,
        )
        .unwrap_err();

        assert!(
            err.to_string().contains("server.request_timeout_secs"),
            "{err}"
        );
    }

    #[test]
    fn invalid_log_level_fails() {
        let err = load(
            &[("EMBROIDERY_LOGGING__LEVEL", "embroidery=loud")],
            NO_LOCAL,
        )
        .unwrap_err();

        assert!(err.to_string().contains("logging.level"), "{err}");
    }
}
