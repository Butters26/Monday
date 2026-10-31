# Old fact-shape filer (switched off Oct 31, 2026)

`FactText.extract_personal_fact_triples` in `notus_fact_text.py` filed facts
by matching regex sentence shapes ("my X is Y", "my X is named Y", favorites,
codewords). It ran before Language's reading and filed things wrong ("my
brother Tom is tall" -> `brother_tom is tall`).

Facts now come only from Language's reading (`DirectNotusProcess._learn_from_reading`).
The function is left in place, unused, so nothing is deleted. Setting
`MONDAY_OLD_FACT_SHAPES=1` turns it back on.
