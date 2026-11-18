//! Entity URIs of the form `kind:key`, such as `domain:apple.com`, `airline:DL` and
//! `sports:nfl:atl`.
//!
//! The normalized key is also the storage lookup key. If normalization changes the key for an
//! existing URI, callers must migrate the stored keys or lookups will miss those rows.
//! Both parsing and [`Uri::new`] normalize keys before callers can store them.

use std::{fmt, str::FromStr};

use idna::AsciiDenyList;
use serde::{Deserialize, Serialize};

/// What an entity's key identifies.
///
/// Adding a variant is a reviewed change: it needs a normalizer, a migration that inserts the kind
/// into the `kinds` table, and a row in the key-decisions document.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Kind {
    /// A website, keyed by host name.
    Domain,
    /// An airline, keyed by IATA code.
    Airline,
    /// A sports team, keyed by `league:team`.
    Sports,
}

impl Kind {
    pub const ALL: [Self; 3] = [Self::Domain, Self::Airline, Self::Sports];

    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Domain => "domain",
            Self::Airline => "airline",
            Self::Sports => "sports",
        }
    }
}

impl fmt::Display for Kind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Kind {
    type Err = UriError;

    /// Case-insensitive, so `Domain:` and `domain:` are the same kind.
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::ALL
            .into_iter()
            .find(|kind| kind.as_str().eq_ignore_ascii_case(s))
            .ok_or(UriError::UnknownKind)
    }
}

/// A parsed, normalized `kind:key`. Build one with [`str::parse`] or [`Uri::new`].
///
/// Serializes as its string form, so catalog files and API bodies hold plain strings.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Uri {
    kind: Kind,
    key: String,
}

impl Uri {
    /// Normalizes `raw_key` with the rule for `kind`.
    ///
    /// # Errors
    ///
    /// Fails with [`UriError::InvalidKey`] if the key doesn't satisfy the kind's rule.
    pub fn new(kind: Kind, raw_key: &str) -> Result<Self, UriError> {
        let key = match kind {
            Kind::Domain => normalize_domain(raw_key),
            Kind::Airline => normalize_airline(raw_key),
            Kind::Sports => normalize_sports(raw_key),
        }
        .map_err(|reason| UriError::InvalidKey { kind, reason })?;
        Ok(Self { kind, key })
    }

    #[must_use]
    pub fn kind(&self) -> Kind {
        self.kind
    }

    #[must_use]
    pub fn key(&self) -> &str {
        &self.key
    }
}

impl fmt::Display for Uri {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}", self.kind, self.key)
    }
}

impl FromStr for Uri {
    type Err = UriError;

    /// Splits at the first `:`, so a key may contain more (`sports:nfl:atl`).
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.split_once(':') {
            Some((kind, key)) if !kind.is_empty() => Self::new(kind.parse()?, key),
            _ => Err(UriError::MissingKind),
        }
    }
}

impl TryFrom<String> for Uri {
    type Error = UriError;

    fn try_from(s: String) -> Result<Self, Self::Error> {
        s.parse()
    }
}

impl From<Uri> for String {
    fn from(uri: Uri) -> Self {
        uri.to_string()
    }
}

/// Why a URI is invalid.
///
/// Errors omit raw input so they can be logged and returned in API responses.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum UriError {
    #[error("expected kind:key, e.g. domain:spotify.com")]
    MissingKind,
    #[error("unknown kind, expected one of: domain, airline, sports")]
    UnknownKind,
    #[error("invalid {kind} key: {reason}")]
    InvalidKey { kind: Kind, reason: &'static str },
}

const MAX_HOST_LEN: usize = 253;
const MAX_LABEL_LEN: usize = 63;

/// Lowercases and punycodes the host (UTS 46, as the WHATWG URL standard applies it), removes a
/// trailing `.`, and strips `www.` when the rest is the registrable domain.
///
/// The `www` rule matches Merino's manifest lookup, which drops `www` only when it is the entire
/// subdomain: `www.bbc.co.uk` becomes `bbc.co.uk`, while `www.media.inaf.it` stays as it is. Merino
/// uses `tldextract` without the public suffix list's private section, and this uses the whole
/// list, so the two disagree on `www.` hosts under a private suffix such as `blogspot.com`. The
/// parity fixture has no such host.
fn normalize_domain(raw: &str) -> Result<String, &'static str> {
    if raw.is_empty() {
        return Err("must not be empty");
    }
    if raw.starts_with('[') {
        return Err("must not be an IP address");
    }
    if raw.contains(['/', '?', '#', ':', '@', '\\']) {
        return Err("must be a host name, without scheme, port, path, query or fragment");
    }

    // `AsciiDenyList::URL` also rejects the code points the URL standard forbids in a host, such
    // as spaces and `%`.
    let ascii = idna::domain_to_ascii_cow(raw.as_bytes(), AsciiDenyList::URL)
        .map_err(|_| "not a valid host name")?;
    let host = ascii.strip_suffix('.').unwrap_or(&ascii);

    if host.is_empty() {
        return Err("must not be empty");
    }
    if host.len() > MAX_HOST_LEN {
        return Err("must be at most 253 bytes");
    }
    if host
        .split('.')
        .any(|label| label.is_empty() || label.len() > MAX_LABEL_LEN)
    {
        return Err("every label must be 1 to 63 bytes");
    }
    // Hosts that end in a number are IPv4 addresses to the URL standard (`127.1`, `0x7f.1`).
    // Registering one would point the scraper at an internal address such as the metadata server.
    if ends_in_number(host) {
        return Err("must not be an IP address");
    }
    if !host.contains('.') {
        return Err("must have at least two labels");
    }

    let host = match host.strip_prefix("www.") {
        Some(rest) if psl::domain_str(host) == Some(rest) => rest,
        _ => host,
    };
    Ok(host.to_owned())
}

/// The URL standard's "ends in a number" check: the last label is decimal digits, or `0x`
/// followed by hex digits.
fn ends_in_number(host: &str) -> bool {
    let last = host.rsplit('.').next().unwrap_or(host);
    let all_digits = !last.is_empty() && last.bytes().all(|b| b.is_ascii_digit());
    let hex = last
        .strip_prefix("0x")
        .is_some_and(|rest| rest.bytes().all(|b| b.is_ascii_hexdigit()));
    all_digits || hex
}

/// Uppercases a two-character IATA code. One character may be a digit, as in `6E` and `E9`.
fn normalize_airline(raw: &str) -> Result<String, &'static str> {
    if raw.len() == 2
        && raw.bytes().all(|b| b.is_ascii_alphanumeric())
        && raw.bytes().any(|b| b.is_ascii_alphabetic())
    {
        Ok(raw.to_ascii_uppercase())
    } else {
        Err(
            "must be a two-character IATA code with at least one ASCII letter and at most one digit",
        )
    }
}

/// Lowercases `league:team`. Both parts are required and use `a-z`, `0-9` and `-` only.
fn normalize_sports(raw: &str) -> Result<String, &'static str> {
    let key = raw.to_ascii_lowercase();
    let mut parts = key.split(':');
    let (Some(league), Some(team), None) = (parts.next(), parts.next(), parts.next()) else {
        return Err("must be league:team");
    };
    if league.is_empty() || team.is_empty() {
        return Err("must be league:team");
    }
    let valid = |part: &str| {
        part.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
    };
    if valid(league) && valid(team) {
        Ok(key)
    } else {
        Err("league and team may use only a-z, 0-9 and -")
    }
}

#[cfg(test)]
mod tests {
    use std::fmt::Write as _;

    use proptest::prelude::*;
    use serde::Deserialize;

    use super::*;

    /// Renders one line per input, `input => key` or `input => error`, for a snapshot.
    fn table(kind: Kind, inputs: &[&str]) -> String {
        inputs.iter().fold(String::new(), |mut out, input| {
            let result = match Uri::new(kind, input) {
                Ok(uri) => uri.key().to_owned(),
                Err(err) => format!("error: {err}"),
            };
            writeln!(out, "{input:?} => {result}").unwrap();
            out
        })
    }

    #[test]
    fn domain_keys() {
        insta::assert_snapshot!(table(
            Kind::Domain,
            &[
                "example.com",
                "WWW.Example.com.",
                "www.bbc.co.uk",
                "www.media.inaf.it",
                "www.www.example.com",
                "www.com",
                "maps.google.com",
                "bücher.de",
                "xn--bcher-kva.de",
                "",
                ".",
                "www",
                "www.",
                "localhost",
                "startsiden.no/sok",
                "https://example.com",
                "example.com:443",
                "user@example.com",
                "example.com?q=1",
                "example.com#top",
                "exa mple.com",
                "a..b",
                "example.com..",
                &format!("{}.com", "a".repeat(64)),
                &format!("{}.com", vec!["a".repeat(63); 4].join(".")),
                "127.0.0.1",
                "169.254.169.254",
                "127.1",
                "0x7f.0.0.1",
                "2130706433",
                "[::1]",
            ],
        ));
    }

    #[test]
    fn airline_keys() {
        insta::assert_snapshot!(table(
            Kind::Airline,
            &[
                "DL", "dl", "6e", "9C", "e9", "12", "", "D", "DAL", "D-", "ÄB"
            ],
        ));
    }

    #[test]
    fn sports_keys() {
        insta::assert_snapshot!(table(
            Kind::Sports,
            &[
                "nfl:atl",
                "NFL:ATL",
                "mls:inter-miami",
                "nfl",
                "nfl:",
                ":atl",
                "nfl:atl:x",
                "nfl:at l",
                "nfl:atl_",
                "nfl:atlé",
            ],
        ));
    }

    #[test]
    fn error_messages() {
        let messages = [
            "spotify.com",
            ":apple.com",
            "stocks:AAPL",
            "domain:",
            "airline:DAL",
            "sports:nfl",
        ]
        .map(|input| format!("{input:?} => {}", input.parse::<Uri>().unwrap_err()));
        insta::assert_snapshot!(messages.join("\n"));
    }

    #[test]
    fn www_and_trailing_dot_are_the_same_uri() {
        assert_eq!(
            "domain:WWW.Example.com.".parse::<Uri>(),
            "domain:example.com".parse::<Uri>()
        );
    }

    #[test]
    fn missing_and_unknown_kinds_fail() {
        assert_eq!("spotify.com".parse::<Uri>(), Err(UriError::MissingKind));
        assert_eq!("stocks:AAPL".parse::<Uri>(), Err(UriError::UnknownKind));
        assert_eq!(
            "unknown\n\x1b[31m:key".parse::<Uri>(),
            Err(UriError::UnknownKind)
        );
    }

    #[test]
    fn kind_is_case_insensitive() {
        let uri: Uri = "Domain:example.com".parse().unwrap();

        assert_eq!(uri.to_string(), "domain:example.com");
    }

    #[test]
    fn serde_uses_the_normalized_string_form() {
        let uri: Uri = serde_json::from_str(r#""airline:dl""#).unwrap();

        assert_eq!(serde_json::to_string(&uri).unwrap(), r#""airline:DL""#);
        assert!(serde_json::from_str::<Uri>(r#""stocks:AAPL""#).is_err());
    }

    /// Every URL Merino's manifest lookup sees, with the key Merino looks it up by. Regenerate with
    /// `scripts/export_domain_parity_fixture.py`.
    #[test]
    fn domain_keys_match_merino() {
        #[derive(Deserialize)]
        struct Entry {
            url: String,
            host: String,
            merino: String,
        }
        let entries: Vec<Entry> =
            serde_json::from_str(include_str!("fixtures/merino_domain_parity.json")).unwrap();
        assert!(!entries.is_empty());

        let mismatches: Vec<String> = entries
            .iter()
            .filter_map(|entry| {
                let ours = Uri::new(Kind::Domain, &entry.host)
                    .map_or_else(|err| format!("error: {err}"), |uri| uri.key().to_owned());
                (ours != entry.merino)
                    .then(|| format!("{}: Merino {}, Embroidery {ours}", entry.url, entry.merino))
            })
            .collect();
        assert!(mismatches.is_empty(), "{}", mismatches.join("\n"));
    }

    fn any_uri_string() -> impl Strategy<Value = String> {
        prop_oneof![
            "[a-zA-Z]{0,8}:[a-zA-Z0-9.:/_-]{0,40}",
            "(domain|DOMAIN):((www|WWW)\\.){0,2}([a-zA-Z0-9-]{1,10}\\.){1,3}[a-zA-Z]{2,6}\\.?",
            "airline:[a-zA-Z0-9]{1,3}",
            "sports:[a-zA-Z0-9-]{0,6}(:[a-zA-Z0-9-]{0,6}){0,2}",
        ]
    }

    proptest! {
        #[test]
        fn display_round_trips(input in any_uri_string()) {
            if let Ok(uri) = input.parse::<Uri>() {
                prop_assert_eq!(uri.to_string().parse::<Uri>(), Ok(uri));
            }
        }

        #[test]
        fn normalizing_is_idempotent(input in any_uri_string()) {
            if let Ok(uri) = input.parse::<Uri>() {
                prop_assert_eq!(Uri::new(uri.kind(), uri.key()), Ok(uri.clone()));
            }
        }

        #[test]
        fn domain_keys_are_bare_lowercase_hosts(input in any_uri_string()) {
            if let Ok(uri) = input.parse::<Uri>()
                && uri.kind() == Kind::Domain
            {
                let key = uri.key();
                prop_assert!(!key.contains(['/', ':']), "{key}");
                prop_assert!(!key.bytes().any(|b| b.is_ascii_uppercase()), "{key}");
                prop_assert!(!key.ends_with('.'), "{key}");
                if let Some(rest) = key.strip_prefix("www.") {
                    // Only a registrable `www.` domain, or `www` in front of a deeper subdomain.
                    prop_assert_ne!(psl::domain_str(key), Some(rest), "{}", key);
                }
            }
        }
    }
}
