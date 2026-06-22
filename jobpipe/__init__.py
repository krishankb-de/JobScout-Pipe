"""jobpipe — automated German tech-job *extraction* pipeline.

ATS-first (Lever, Personio, Workday, SuccessFactors, Join.com) with an adaptive
scrapling DOM fallback for bespoke career sites. Filters to entry/junior/mid/
graduate software roles posted within a rolling window and writes an Excel sheet.

Extraction only: this package never applies, autofills, logs in, or submits.
"""

__version__ = "0.1.0"
