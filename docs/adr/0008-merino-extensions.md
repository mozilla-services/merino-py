# Extend Merino via Rust Extensions

* Status: Proposed
* Deciders: All Merino engineers
* Date: 2025-07-28

## Context and Problem Statement

As Merino continues to expand with an ever-growing user base,
performance hot-spots and resource intensive code paths have emerged in the code base,
which impose new challenges in service scalability and operational cost hikes.

As a common solution, Python extensions can be developed for performance critical modules,
but they also bring their own challenges such as the familiarity with a low-level
language (e.g. C/C++ or Rust), tooling, and the potential issues (e.g. memory safety).

In this ADR, we explore various options to develop Python extensions for Merino and aim to
identify a reasonable approach for us extend Merino to meet the performance needs while
maintaining the overall developer experience that we equally value for the project.

Note that:

Instead of re-writing performance critical parts as language-level extensions, we could also
carve certain functionalities out and tackle them separately outside of Merino. For instance,
a new service can be added to handle a computationally intensive task for Merino. Or a
dedicated external storage system can be used to replace an in-memory dataset in Merino.

That approach is out of scope for this ADR as it normally requires a wider discussion
on service architecture or system design changes. This ADR only focuses on extensions
on the language level.


## Decision Drivers

1. The ability to meet the desirable performance requirements and to get fine-grained
   control over compute resources.
2. Developer experience. Developing Merino extensions should *not* have negative impact
   on the overall developer experience of Merino.
3. System safety. Performance boost should *not* be achieved at the cost of system
   safety regressions.

## Considered Options

* A. Extend Merino via Rust extensions through PyO3/Maturin ecosystem.
* B. Extend Merino via C/C++ extensions.
* C. Maintain status quo – build Merino in pure Python.

## Decision Outcome

Chosen option:

* A. "Extend Merino via Rust extensions through PyO3/Maturin ecosystem".

### Positive Consequences

* Rust is a system programming language suitable for developing performance critical
  software. PyO3/Maturin is a mature ecosystem for building Python extensions.
* Rust has been widely adopted at Mozilla for both server and client side development.
  Its learning curve is relatively lower than other counterparts such as C/C++ for
  Python extension development.
* Rust's strong memory safety guarantees are superior than other competitors.

### Negative Consequence

* Rust would be a requirement for Merino's extension development, which comes with
  its own learning curve.
* Require the familiarity with PyO3/Maturin.

### Mitigations

* To minimize interruptions, Merino extensions will be developed as a separate Python
  package using a dedicated git repo. The extensions will be added to Merino as a PyI
  dependence. For Merino developers who do not work on extensions, their development
  experience will remain unchanged.
* While the basic familiarity with PyO3/Maturin is still required for Merino extension
  developers, common development actions can be provided via `uv` and Makefile tasks.
  Package building and publishing will be automated in CI.
* The DISCO team will host "Office Hours" regularly to help Merino developers with
  questions about Rust & extension development.


## Pros and Cons of the Options

### Option A: Extend Merino via Rust extensions Through PyO3/Maturin

This approach allows Merino developers to identify the performance critical code in
Merino and re-implement it as Python extensions in Rust via PyO3 to boost system
performance or resolve bottlenecks.

#### Pros

* Using Python extensions is a common way to achieve higher performance and lower resource
  footprint in Python.
* Rust has gained its popularity in building Python extensions lately. Many popular
  Python extensions, including the ones used by Merino, e.g. `pydantic` and `orjson`,
  are built in Rust via Pyo3.
* Building Python extensions normally requires manual management of compute resources
  using a low-level language, hence extensions are prone to memory safety bugs.
  Rust is superior over its competitors w.r.t avoiding memory safety issues as it is a
  memory safe language.

#### Cons

* Rust has a steep learning curve.
* Many disruptive changes from build, test, and release to Merino's development processes
  if we were to introduce Rust and PyO3 to the Merino project, which could negatively
  affect Merino's developer experience especially for folks that do not work on extensions.


### Option B: Extend Merino via C/C++ Extensions

C/C++ and Cython are the most popular languages for developing Python extension development.
While being the most mature solution, it requires the use of C/C++ that is even more alien
than Rust to most Merino developers.

#### Pros

* The most mature ecosystem as it's the standard way to build Python extensions.
* Best performance.

#### Cons

* C/C++ has an equally steep learning curve as Rust.
* C/C++ is memory unsafe and more likely to introduce safety issues to Merino.

### Option C: Maintain Status Quo – Build Merino in pure Python

We could continue to build everything in Python for Merino. For performance critical code,
we could either optimize it in pure Python or resort to third party packages if any.

#### Pros

* Python is all we need for Merino development.
* No changes required for build, package, and release processes.

#### Cons

* Could be difficult to optimize things if bare-metal or fine-grained resource control
  is needed.
* Of-the-shelf solutions are not always available specifically for business logic
  code paths.
