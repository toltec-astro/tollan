# 02b14a — Round-trip coordinate degrees at binary64 precision

The source-catalog round-trip audit found a second existing precision loss:
`SkyCoordField` formatted ICRS degrees with 15 significant digits. All four
reference telescope targets changed when restored; earlier tests allowed a tiny
angular tolerance and did not catch it.

Change only the numeric formatting to 17 significant digits, sufficient to
round-trip binary64 degrees. The emitted string remains explicit ICRS degrees;
named coordinates retain their original name and resolver behavior. No global
Astropy defaults, caches, frame conversion policy or parser ordering changes.
Numeric strings may now be longer. This does not preserve arbitrary original
frames or ancillary coordinate attributes; those were not this field's contract.

Four generic numerical regressions assert exact RA/Dec degree equality, including
near-boundary and small exponential values. The existing named-source tests stay
unchanged. **1,293 full Tollan tests pass in 3.77 s**, scoped Ruff/format and full
ty pass. Log: `/tmp/tollan-20260922-skycoord-full.log`.

The dependent Tolteca source-record tests compare real telescope target and
reference coordinates exactly before/after JSON and mixed Arrow/Parquet storage.
No tolerance is relaxed, fixture modified, dependency changed or network lookup
needed. This is a focused prerequisite for typed catalog composition, not a
general astronomy-codec redesign.
