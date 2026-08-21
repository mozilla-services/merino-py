"""Some generic, sample backends"""

# For convenience, let's re-export a few lower dependencies here.
from merino.providers.suggest.skeleton.backends.errors import GeneralError

# A "backend" is the Model that encapsulates the methods required to access and store
# data. Note that while it's possible to call this from both `jobs` and `suggest`, the
# Datastore may not always have the same levels of access. (e.g. `jobs` is READ/WRITE,
# where `suggest` is READ only.)
#
# Each "backend" will be specific to the provider, and derives from a `Protocol` base.
# The Protocol contains startup/shutdown methods.
