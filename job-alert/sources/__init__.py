# sources/__init__.py
from .france_travail import fetch_jobs as fetch_france_travail
from .welcome_to_the_jungle import fetch_jobs as fetch_wttj
from .indeed import fetch_jobs as fetch_indeed

__all__ = ["fetch_france_travail", "fetch_wttj", "fetch_indeed"]
