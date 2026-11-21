from typing import Annotated

from pydantic import StringConstraints

BankReference = Annotated[str, StringConstraints(pattern=r"^(demo|ref):[a-zA-Z0-9:_-]{1,100}$")]
