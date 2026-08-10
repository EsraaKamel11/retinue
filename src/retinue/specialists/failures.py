"""The retryable split. A format failure can be fixed by the model; a missing source cannot -
'a document that does not mention the schedule is not going to start mentioning it after a
retry', and retrying it is an invitation to fabricate."""
class ResearchValidationError(Exception):
    retryable: bool = False

class MalformedCitation(ResearchValidationError):
    retryable = True
    def __init__(self, claim: str, prior: str) -> None:
        super().__init__(f"malformed citation on {claim!r}: {prior!r}")
        self.claim, self.prior = claim, prior

class MissingSource(ResearchValidationError):
    retryable = False
    def __init__(self, claim: str, source: str) -> None:
        super().__init__(f"no fixture document supports {claim!r} (cited {source!r}); escalating, not retrying")
        self.claim, self.source = claim, source
