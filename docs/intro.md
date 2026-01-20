# Merino

Merino is a service that provides address bar suggestions and curated recommendations
to Firefox. Some of this content comes from third party providers. In this case, Merino
serves as a privacy preserving buffer. User input in the address bar is handled by Merino
and any clicked impression will be delegated to a Mozilla-controlled service which will
then send an interaction ping if defined in the request and not to a provider directly.
See [API documentation](https://merino.services.mozilla.com/docs) for more details.

## Table of Contents
[api.md - API Documentation][1] describes endpoints, query parameters, request and response headers, response objects and details on the suggestion objects.

[firefox.md - Firefox and Merino Environments][2] describes how to enable
Merino in Firefox and lists the endpoints for the service in Production,
State and Dev.

[data.md - Data, Metrics, Logging][4] describes all metrics and logs.

[dev/index.md - Basic Developer Docs][5] describes basics of working on Merino.

[dev/dependencies.md - Development Dependencies][6] describes the development
dependencies required for Merino.

[dev/logging-and-metrics.md - Logging and Metrics][7] describes metrics, logging, and telemetry.

[dev/release-process.md - Release Process][8] describes the release process of Merino in detail.

[dev/testing.md - Testing][9] describes unit, integration and load tests for Merino.

[dev/profiling.md - Profiling][10] describes how to profile Merino to address performance issues.

[operations/configs.md - Configuring Merino][3] describes configuration management
of the project, Dynaconf setup, and the configuration of the HTTP server, logging, metrics, Remote Settings, and Sentry.

[operations/elasticsearch.md - Elasticsearch Operations][11] describes some functionality and operations that
we do on the Elasticsearch cluster.

[operations/jobs.md - Merino Jobs][12] describes the jobs that are configured in Merino. Indicate where the jobs
exist and link to the details for how the jobs are run.

[1]: ./api.md
[2]: ./firefox.md
[3]: ./operations/configs.md
[4]: ./data.md
[5]: ./dev/index.md
[6]: ./dev/dependencies.md
[7]: ./dev/logging-and-metrics.md
[8]: ./dev/release-process.md
[9]: ./dev/testing.md
[10]: ./dev/profiling.md
[11]: ./operations/elasticsearch.md
[12]: ./operations/jobs.md

## About the Name

This project drives an important part of Firefox's "felt experience". That is,
the feeling of using Firefox, hopefully in a delightful way. The word "felt" in
this phrase refers to feeling, but it can be punned to refer to the
[textile](https://en.wikipedia.org/wiki/Felt). Felt is often made of wool, and
Merino wool (from Merino sheep) produces exceptionally smooth felt.

## Architecture

```mermaid
flowchart TD
subgraph Firefox["fa:fa-firefox-browser Firefox"]
        NewTab
        UrlBar
end
subgraph NewTab["fa:fa-plus New Tab"]
        CuratedRecommendations("Curated Recommendations")
        WeatherWidget("Weather Widget")
end
subgraph UrlBar["fa:fa-magnifying-glass Url Bar"]
        online("Online Search and Suggest")
        offline("Offline Search and Suggest<br>fetches adMarketplace, static Wikipedia, <br>and other suggestions.<br> Offline mode is fallback if Merino times out.")
end
subgraph middleware["fa:fa-layer-group Middleware"]
        Geolocation["Geolocation"]
        Logging["Logging"]
        UserAgent["UserAgent"]
        Metrics["Metrics"]
end
subgraph suggestProviders["fa:fa-truck Suggest Providers"]
        admProvider("adm")
        amoProvider("amo")
        geolocationProvider("geolocation")
        toppicksProvider("top-picks")
        weatherProvider("weather")
        wikipediaProvider("wikipedia")
        financeProvider("finance")
end
subgraph suggestBackends["fa:fa-microchip Suggest Backends"]
        remoteSettingsBackend("remote settings")
        accuweatherBackend("accuweather")
        elasticBackend("elastic")
        toppicksBackend("top picks")
        dynamicAmoBackend("dynamic addons")
        massiveBackend("massive")
end
subgraph curatedRecommendationsBackends["fa:fa-microchip Curated Recommendations Backends"]
        corpusBackend("corpus")
        extendedExpirationCorpusBackend("corpus extended expiration")
        gcsEngagementBackend("gcs engagement")
        fakespotBackend("fakespot")
        gcsPriorBackend("gcs prior")
end
subgraph Merino["fa:fa-server Merino"]
        srh("fa:fa-gears Suggest Request Handler")
        crh("fa:fa-gears Curated Recommendations Handler")
        mrh("fa:fa-gears Manifest Handler")
        middleware
        maxmind[("fa:fa-database MaxmindDB")]
        suggestProviders
        curatedRecommendationsProvider["fa:fa-truck Curated Recommendations Provider"]
        manifestProvider["fa:fa-truck Manifest Provider"]
        suggestBackends
        curatedRecommendationsBackends
        manifestBackend["Manifest Backend"]
end
subgraph Jobs["fa:fa-rotate Airflow (Merino Jobs)"]
        wikipediaSyncJob("Wikipedia Sync")
        toppicksSyncJob("Top Picks Sync")
end
    User[\"fa:fa-user User"/] -- Accessing the Firefox URL bar --> Firefox
    online -- /api/v1/suggest --> srh
    CuratedRecommendations -- "/api/v1/curated-recommendations" --> crh
    manifest["manifest"] -- /api/v1/manifest --> mrh
    WeatherWidget --> srh
    srh -..- middleware
    crh -..- middleware
    mrh -..- middleware
    srh --> suggestProviders
    crh --> curatedRecommendationsProvider
    mrh --> manifestProvider
    curatedRecommendationsProvider --> curatedRecommendationsBackends
    manifestProvider --> manifestBackend
    admProvider --> remoteSettingsBackend
    amoProvider --> dynamicAmoBackend
    toppicksProvider --> toppicksBackend
    weatherProvider --> accuweatherBackend
    wikipediaProvider --> elasticBackend
    financeProvider --> massiveBackend
    massiveBackend --> massiveApi("fa:fa-globe Massive API")
    Geolocation --> maxmind
    dynamicAmoBackend --> addonsAPI("fa:fa-globe Addons API")
    elasticBackend --> elasticSearch[("Elasticsearch")]
    manifestBackend -..-> toppicksData[("fa:fa-database GCS Top Picks Data,<br>a list of Mozilla curated popular sites and metadata to be <br>displayed on browser")]
    toppicksSyncJob -..-> toppicksData
    accuweatherBackend -..-> accuweatherAPI("fa:fa-globe Accuweather API")
    accuweatherAPI -. tries to query cache first ..-> redis[("fa:fa-memory Redis Cache")]
    gcsEngagementBackend --> gcsMerinoAirflowData[("fa:fa-database GCS Merino Airflow Data")]
    gcsPriorBackend --> gcsMerinoAirflowData
    fakespotBackend --> gcsFakespotNewTabProducts[("fa:fa-database GCS Fakespot NewTab Products")]
    corpusBackend -..-> curatedCorpusAPI("fa:fa-globe Curated Corpus API")
    offline -..- kinto[("Remote Settings")]
    remoteSettingsBackend --- merinoRustExtension("fa:fa-puzzle-piece Merino Rust Extension")
    merinoRustExtension --> kinto
    wikipediaSyncJob -. Syncs Wikipedia entries weekly ..- elasticSearch
```
