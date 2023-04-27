# Merino Suggest API Response Structure

* Status: proposed
* Deciders: [list everyone involved in the decision] <!-- optional -->
* Date: 2023-04-20

## Context and Problem Statement

As Merino continues to add more suggestions, 
suggestion providers are going to have to return all sorts of
data to the clients that are bespoke to the particular suggestion.
For instance, weather suggestion returns a `temperature`.
Currently, we do not have a strategy to manage these bespoke pieces of data
which results in them returned at the top level of the suggestion object.
However, this will pose a problem when

1. names of fields are shared between providers, but have different semantics 
  (i.e. `rating` may be a decimal value between 0-1 in one type, 
   and a "star" integer rating between 1-5 in another)
1. the API is unclear about what will _necessarily_ exist, and what is _optional_,
   which leads to client confusion about the contract

So, this ADR is to make a decision on how we want to handle provider specific fields
going forward.

## Decision Drivers

In rough order of importance:

1. Explicitness of Ownership - i.e. the `rating` field belongs to the `addons` provider
1. Compatibility with [JSON] Schema Validation
1. Adherence to the Fx Suggest Design Framework
1. Backwards Compatibility with Current Schema

## Considered Options

* A. Continue to add to Top Level with Optional Fields
* B. Custom Details Field for Bespoke Provider Fields
* B.5 Custom Details Field without the Provider Nesting
* C. Custom Details Field for a "Type"
* D. Component Driven `custom_details`

## Decision Outcome

Chosen option: ???

### Positive Consequences <!-- optional -->

* ???

### Negative Consequences <!-- optional -->

* ???

## Pros and Cons of the Options 

### A. Continue to add to Top Level with Optional Fields

This is the status quo option.
We will continue to append bespoke values to the top level suggestion,
and ensure that they're optional.
We can continue to use the `provider` to signal what fields exists
and how they should be parsed.
For example, we can specify 2 different types of `rating`,
and hence 2 validation strategy for it,
based off of which provider is specified.

Example:

```json
{
  "suggestions": [
    {
      ...
      "provider": "addons",
      "rating": "4.123",
      ...
    },
    {
      ...
      "provider": "movies",
      "rating": 0.123,
      ...
    },
    ...
  ],
  ...
}
```

The partial JSON Schema validation will look something like:

```json
{
  "type": "object",
  "properties": {
    "provider": {
      "type": "string"
    }
  },
  "required": ["provider"],
  "allOf": [
    {
      "if": {
        "properties": {
          "provider": {
            "const": "addons"
          }
        }
      },
      "then": {
        "properties": {
          "rating": {
            "type": "string"
          }
        },
        "required": [
          "rating"
        ]
      }
    },
    {
      "if": {
        "properties": {
          "provider": {
            "const": "movies"
          }
        }
      },
      "then": {
        "properties": {
          "rating": {
            "type": "number"
          }
        },
        "required": [
          "rating"
        ]
      }
    }
  ]
}
```

#### Pros

* Can specify specific validation per provider.
* Merino is still kind of immature, so it still might be too early to think about design.
* Less nesting in the models (resulting in less complexity).
* Currently, backwards compatible as we don't have to do anything 
  to existing providers, as this follows the existing patterns.

#### Cons

* Lack of isolation for bespoke fields; `ratings` is coupled with 2 specific providers,
  and by just looking at the response, it's not clear that they are related.
* Not clear what is shared between _all_ suggestions, vs. what is bespoke to specific provider.
* It is not obvious that the `provider` field should signal how you should perform validation.
  In other words, there is a contextual dependency on the JSON structure of suggestion based on `provider`.


### B. Custom Details Field for Bespoke Provider Fields

We introduce a `custom_details` field that uses a provider name as key
to an object with the bespoke values to that provider.

Example:

```json
{
  "suggestions": [
    {
      ...
      "provider": "addons",
      "custom_details": {
        "addons": {
          "rating": "4.7459"
        }
      }
    },
    ...
  ],
  ...
}
```

The specific fields in `custom_details` will all be optional (i.e. `addons` will be an optional key)
but the _shape_ of what goes in `addons` can be more strict (i.e. `addons` require a `rating` field).

A partial schema specification for the above might look like[^jsonschema]:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Suggest API Response v1",
  "description": "Response for /api/v1/suggest",
  "type": "object",
  "properties": {
    "provider": {
      "description": "id for the provider type",
      "type": "string"
    },
    "custom_details": {
      "type": "object",
      "properties": {
        "addons": {
          "type": "object",
          "description": "Custom Addon Fields",
          "properties": {
            "rating": {
              "type": "number"
            }
          },
          "required": ["rating"]
        }
      }
    }
  },
  "required": ["provider"]
}
```

[^jsonschema]: Can play with JSON schema in https://www.jsonschemavalidator.net/

#### Pros

* Can specify specific validation per provider.
* Clear ownership of `rating` to `addons` via structure.
* Fields outside of `custom_details` can be fields that are more universal across suggestions.
  These fields can potentially be correlated directly to the Fx Suggest Design Framework
  (i.e. `context_label`, `url`, `title`, `description`, etc.).
* Having a clear distinction for Fx Suggest Design Framework fields vs. bespoke fields makes this more
  backwards compatible, as the fields in the Design Framework can render the _default_ suggestion case
  for clients who haven't upgraded their clients.

#### Cons

* We'll likely need to migrate existing providers at some point. But in the meantime,
  some fields will not follow convention to maintain backwards compatibility.
* Extra nesting inside of `custom_details`.

### B.5 Custom Details Field without the Provider Nesting

This is exactly like B, except that we remove the extra nesting.

So, in the example above, we can remove the extra `addons` object to get:

```json
{
  "suggestions": [
    {
      ...
      "provider": "addons",
      "custom_details": {
        "rating": "4.7459"
      }
    },
    ...
  ],
  ...
}
```

The validation of the contents of `custom_details` will look more like A.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Suggest API Response v1",
  "description": "Response for /api/v1/suggest",
  "type": "object",
  "properties": {
    "provider": {
      "description": "id for the provider type",
      "type": "string"
    }
  },
  "required": [
    "provider"
  ],
  "if": {
    "properties": {
      "provider": {
        "const": "addons"
      }
    }
  },
  "then": {
    "properties": {
      "custom_details": {
        "description": "Custom Details Specific for Addons",
        "type": "object",
        "properties": {
          "rating": {
            "type": "string"
          }
        },
        "required": [
          "rating"
        ]
      }
    },
    "required": ["custom_details"]
  }
}
```

#### Pros

* Can specify specific validation per provider.
* Fields outside of `custom_details` can be fields that are more universal across suggestions.
  These fields can potentially be correlated directly to the Fx Suggest Design Framework
  (i.e. `context_label`, `url`, `title`, `description`, etc.).
* Having a clear distinction for Fx Suggest Design Framework fields vs. bespoke fields makes this more
  backwards compatible, as the fields in the Design Framework can render the _default_ suggestion case
  for clients who haven't upgraded their clients.
* Less nesting in the response than B

#### Cons

* We'll likely need to migrate existing providers at some point. But in the meantime,
  some fields will not follow convention to maintain backwards compatibility.
* The relationship between `provider` and `custom_details` is more implicit, than explicit.
* This has a lot of the same _cons_ as Option A because validation is done similarly.

### C. Custom Details Field for a "Type"

This is similar to option B, except that we want to introduce a new `type` field
to differentiate it from the provider.
The `custom_details` will be keyed by this type, rather than the `provider` name.
These `types` are kind of analogous to a _rendering component_,
as they will likely be used to specify a specific rendering path in the client.

Example:

```json
{
  "suggestions": [
    {
      ...
      "provider": "addons",
      "type": "addons_type",
      "custom_details": {
        "addons_type": {
          "rating": "4.7459"
        }
      }
    },
    ...
  ],
  ...
}
```

#### Pros

* All the pros for B applies here
* Can decouple the `custom_details` from `provider`. This will be helpful for potentially 
  sharing the `type` with other suggestions produced by different providers. For instance,
  we may want this to specify different _rendering_ paths in the client 
  (i.e. a "top picks" type to be shared between `addons` and `top_picks` providers,
  as there's many shared fields because they're rendered similarly). 

#### Cons

* All the cons for B applies here
* Potentially over-engineering for `type`, as it's use is currently hypothetical.

### D. Component Driven `custom_details`

This solution will model distinct UI components in the `custom_details` section.
For example, if the `addons` provider have specific UI components to render a `ratings` component and
a `highlight_context_label`, then we can specify these directly in the `custom_details` section.
This will assume that the client side have these specific rendering types.


Example:

```json
{
  "suggestions": [
    {
      ...
      "provider": "addons",
      "custom_details": {
        "ratings": {
          "value": "4.7459",
          "unit": "stars"
        },
        "highlight_context_label": {
          "text": "Special Limited Time Offer!"
        }
      }
    },
    ...
  ],
  ...
}
```

#### Pros

* Can share custom components with schema validation.
* Backwards compatible with clients who don't have the necessary components to render. 
  It will just use the default renderer via the Fx Suggest Design Framework

#### Cons

* We currently don't have a sophisticated Component Design Framework, so this is probably overengineering.
* This tightly couples the API to the design framework of Desktop Firefox, which makes the fields potentially
  less relevant to other clients.

## Links 

* [JSON Schema Specification](https://json-schema.org/)
