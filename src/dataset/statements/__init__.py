"""The statements of the dataset checked against the originals on Codeforces (specs/006).

``fetch`` gets each original page once and keeps it with its hash; ``extract`` reads the statement
block of a page; ``render`` turns it into the flattened text (as the dataset has it) and the marked
text (exponents ``^{...}``, indices ``_{...}``); ``compare`` aligns the marked text with
``enunciado.md`` and classifies every difference by the element of the original under it;
``correct`` inserts the lost marks into the current text and checks the result. Nothing here
writes into the dataset.
"""


class UsageError(Exception):
    """A wrong option or destination of check-statements/correct-statements: exit code 2."""
