"""Version 1 of the index mapping & settings"""


def get_suggest_mapping(analyzer_suffix: str) -> dict:
    """Return an Elasticsearch mapping for suggestions using language-specific analyzers based on the given suffix."""
    return {
        "dynamic": False,
        "properties": {
            "batch_id": {"type": "long"},
            "version": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "title": {"type": "keyword"},
            "suggest": {
                "type": "completion",
                "analyzer": f"plain_{analyzer_suffix}",
                "search_analyzer": f"plain_search_{analyzer_suffix}",
                "preserve_separators": True,
                "preserve_position_increments": True,
                "max_input_length": 255,
            },
            "suggest-stop": {
                "type": "completion",
                "analyzer": f"stop_analyzer_{analyzer_suffix}",
                "search_analyzer": f"stop_analyzer_search_{analyzer_suffix}",
                "preserve_separators": False,
                "preserve_position_increments": False,
                "max_input_length": 255,
            },
        },
    }


FR_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "frwiki_policy",
    "analysis": {
        "filter": {
            "french_elision": {
                "type": "elision",
                "articles_case": True,
                "articles": [
                    "l",
                    "m",
                    "t",
                    "qu",
                    "n",
                    "s",
                    "j",
                    "d",
                    "c",
                    "jusqu",
                    "quoiqu",
                    "lorsqu",
                    "puisqu",
                ],
            },
            "french_stop": {"type": "stop", "stopwords": "_french_"},
            "french_keywords": {"type": "keyword_marker", "keywords": ["exemple"]},
            "french_stemmer": {"type": "stemmer", "language": "light_french"},
            "token_limit": {"type": "limit", "max_token_count": 20},
            "remove_empty": {"type": "length", "min": 1},
            "accentfolding": {"type": "asciifolding"},
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    "-=>\\u0020",
                    "'=>\\u0020",
                    '"=>\\u0020',
                ],
            }
        },
        "analyzer": {
            "plain_fr": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
            "stop_analyzer_fr": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": [
                    "french_elision",
                    "lowercase",
                    "french_stop",
                    "french_keywords",
                    "french_stemmer",
                ],
            },
            "stop_analyzer_search_fr": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["french_elision", "lowercase", "french_keywords", "french_stemmer"],
            },
            "plain_search_fr": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
        },
    },
}


DE_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "dewiki_policy",
    "analysis": {
        "filter": {
            "german_stop": {"type": "stop", "stopwords": "_german_"},
            "german_stemmer": {"type": "stemmer", "language": "light_german"},
            "token_limit": {"type": "limit", "max_token_count": 20},
            "remove_empty": {"type": "length", "min": 1},
            "accentfolding": {"type": "asciifolding"},
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    "-=>\\u0020",
                    "'=>\\u0020",
                    '"=>\\u0020',
                ],
            }
        },
        "analyzer": {
            "plain_de": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
            "stop_analyzer_de": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": [
                    "lowercase",
                    "german_stop",
                    "german_normalization",
                    "german_stemmer",
                ],
            },
            "stop_analyzer_search_de": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "german_normalization", "german_stemmer"],
            },
            "plain_search_de": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
        },
    },
}

EN_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "enwiki_policy",
    "analysis": {
        "filter": {
            "stop_filter": {
                "type": "stop",
                "remove_trailing": "true",
                "stopwords": "_english_",
            },
            "token_limit": {"type": "limit", "max_token_count": "20"},
            "lowercase": {"name": "nfkc_cf", "type": "icu_normalizer"},
            "remove_empty": {"type": "length", "min": "1"},
            "accentfolding": {"type": "icu_folding"},
        },
        "analyzer": {
            "stop_analyzer": {
                "filter": [
                    "icu_normalizer",
                    "stop_filter",
                    "accentfolding",
                    "remove_empty",
                    "token_limit",
                ],
                "type": "custom",
                "tokenizer": "standard",
            },
            "plain_search": {
                "filter": ["remove_empty", "token_limit", "lowercase"],
                "char_filter": ["word_break_helper"],
                "type": "custom",
                "tokenizer": "whitespace",
            },
            "plain": {
                "filter": ["remove_empty", "token_limit", "lowercase"],
                "char_filter": ["word_break_helper"],
                "type": "custom",
                "tokenizer": "whitespace",
            },
            "stop_analyzer_search": {
                "filter": [
                    "icu_normalizer",
                    "accentfolding",
                    "remove_empty",
                    "token_limit",
                ],
                "type": "custom",
                "tokenizer": "standard",
            },
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    '"=>\\u0020',
                    "-=>\\u0020",
                    "'=>\\u0020",
                    "\\u2019=>\\u0020",
                    "\\u02BC=>\\u0020",
                    ";=>\\u0020",
                    "\\[=>\\u0020",
                    "\\]=>\\u0020",
                    "{=>\\u0020",
                    "}=>\\u0020",
                    "\\\\=>\\u0020",
                    "\\u00a0=>\\u0020",
                    "\\u1680=>\\u0020",
                    "\\u180e=>\\u0020",
                    "\\u2000=>\\u0020",
                    "\\u2001=>\\u0020",
                    "\\u2002=>\\u0020",
                    "\\u2003=>\\u0020",
                    "\\u2004=>\\u0020",
                    "\\u2005=>\\u0020",
                    "\\u2006=>\\u0020",
                    "\\u2007=>\\u0020",
                    "\\u2008=>\\u0020",
                    "\\u2009=>\\u0020",
                    "\\u200a=>\\u0020",
                    "\\u200b=>\\u0020",
                    "\\u200c=>\\u0020",
                    "\\u200d=>\\u0020",
                    "\\u202f=>\\u0020",
                    "\\u205f=>\\u0020",
                    "\\u3000=>\\u0020",
                    "\\ufeff=>\\u0020",
                ],
            }
        },
    },
}


IT_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "itwiki_policy",
    "analysis": {
        "filter": {
            "italian_elision": {
                "type": "elision",
                "articles_case": True,
                "articles": [
                    "c",
                    "l",
                    "all",
                    "dall",
                    "dell",
                    "nell",
                    "sull",
                    "coll",
                    "pell",
                    "gl",
                    "agl",
                    "dagl",
                    "degl",
                    "negl",
                    "sugl",
                    "un",
                    "m",
                    "t",
                    "s",
                    "v",
                    "d",
                ],
            },
            "italian_stop": {"type": "stop", "stopwords": "_italian_"},
            "italian_stemmer": {"type": "stemmer", "language": "light_italian"},
            "token_limit": {"type": "limit", "max_token_count": 20},
            "remove_empty": {"type": "length", "min": 1},
            "accentfolding": {"type": "asciifolding"},
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    "-=>\\u0020",
                    "'=>\\u0020",
                    '"=>\\u0020',
                ],
            }
        },
        "analyzer": {
            "plain_it": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
            "stop_analyzer_it": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": [
                    "italian_elision",
                    "lowercase",
                    "italian_stop",
                    "accentfolding",
                    "italian_stemmer",
                ],
            },
            "stop_analyzer_search_it": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["italian_elision", "lowercase", "accentfolding", "italian_stemmer"],
            },
            "plain_search_it": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
        },
    },
}


PL_INDEX_SETTINGS: dict = {
    "number_of_replicas": "1",
    "refresh_interval": "-1",
    "number_of_shards": "2",
    "index.lifecycle.name": "plwiki_policy",
    "analysis": {
        "filter": {
            "token_limit": {"type": "limit", "max_token_count": 20},
            "remove_empty": {"type": "length", "min": 1},
            "accentfolding": {"type": "asciifolding"},
        },
        "char_filter": {
            "word_break_helper": {
                "type": "mapping",
                "mappings": [
                    "_=>\\u0020",
                    ",=>\\u0020",
                    "-=>\\u0020",
                    "'=>\\u0020",
                    '"=>\\u0020',
                ],
            }
        },
        "analyzer": {
            "plain_pl": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
            "stop_analyzer_pl": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "accentfolding", "remove_empty", "token_limit"],
            },
            "stop_analyzer_search_pl": {
                "type": "custom",
                "tokenizer": "standard",
                "filter": ["lowercase", "accentfolding", "remove_empty", "token_limit"],
            },
            "plain_search_pl": {
                "type": "custom",
                "tokenizer": "whitespace",
                "char_filter": ["word_break_helper"],
                "filter": ["remove_empty", "token_limit", "lowercase"],
            },
        },
    },
}


LANGUAGE_SETTINGS_BUILDERS: dict[str, dict] = {
    "en": EN_INDEX_SETTINGS,
    "fr": FR_INDEX_SETTINGS,
    "de": DE_INDEX_SETTINGS,
    "it": IT_INDEX_SETTINGS,
    "pl": PL_INDEX_SETTINGS,
}


def get_suggest_settings(language_code: str) -> dict:
    """Return elasticsearch settings for the given language code."""
    try:
        return LANGUAGE_SETTINGS_BUILDERS[language_code]
    except KeyError:
        raise ValueError(f"No analyzer settings defined for language: {language_code}")
