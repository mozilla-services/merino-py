from typing import Callable, Optional, Sequence

from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.sdk.trace.sampling import Sampler, SamplingResult, TraceIdRatioBased, ALWAYS_ON
from opentelemetry.util.types import Attributes
from opentelemetry.context import Context


class SamplingRule:
    """A sampling rule for use in RuleBasedSampler"""

    def __init__(self, name: str, matcher: Callable, sampler: Sampler):
        self.name = name
        self.matcher = matcher
        self.sampler = sampler


class RuleBasedSampler(Sampler):
    """
    Rule-based sampler (order matters). For each sampler in this class,
    tests an incoming span to see if it matches one of the rules (in order
    passed to the constructor). If no rule matches, apply the default sampler.
    """

    def __init__(self, rules: list[SamplingRule], default_sampler: Sampler):
        self.rules = rules
        self.default_sampler = default_sampler

    def should_sample(
        self,
        parent_context: Optional[Context],
        trace_id: int,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Attributes = None,
        links: Optional[Sequence[Link]] = None,
        trace_state: Optional[TraceState] = None,
    ) -> SamplingResult:
        """Sample based on list of rules"""
        # Check each rule
        for rule in self.rules:
            if rule.matcher(name, attributes):
                return rule.sampler.should_sample(
                    parent_context, trace_id, name, kind, attributes, links, trace_state
                )
        # Fall back to default
        return self.default_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        """Return sampler description"""
        sampler_descriptions = ",".join(
            [f"{r.name}:{r.sampler.get_description}" for r in self.rules]
        )
        return f"RuleBasedSampler{{{sampler_descriptions}}}"


class BgTaskDownSamplerFactory:
    """
    Entrypoint for custom sampler configurable using environment vars, e.g:
    `OTEL_TRACES_SAMPLER=bg_task_sampler,OTEL_TRACES_SAMPLER_ARG=0.01`
    See https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.sampling.html

    The argument passed is the rate at which to sample root spans with the attribute
    `is_bg_task=true`. This head sampler does not take into account the ultimate
    outcome of the trace, such as whether an error ocurred. 

    The Mozilla collector is currently configured to also do tail sampling,
    sampling 100% of error spans and a smaller percent (e.g. 1%) of non-error
    spans. Due to the frequency of background tasks, they are overrepresented
    in the sampled set as compared to, e.g. user-triggered queries. This sampler
    cuts down on the number of background task spans sent to the collector.
    """
    @staticmethod
    def get_sampler(sampler_argument):
        rate = 0.01
        try:
            # Override default value
            rate = float(sampler_argument)
        except (TypeError, ValueError): # In case argument is empty string or unset
            pass  # just uses the default
        return RuleBasedSampler(
                rules=[
                    SamplingRule(
                        "IsBgTask",
                        matcher=lambda _, attrs: attrs and attrs.get("is_bg_task"),
                        # Sample 1% of background tasks
                        sampler=TraceIdRatioBased(rate),
                    )
                ],
                # We use tail sampling in the collector, so default to send all spans otherwise
                default_sampler=ALWAYS_ON
        )
