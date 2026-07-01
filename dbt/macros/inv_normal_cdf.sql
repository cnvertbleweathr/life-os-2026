{#
  inv_normal_cdf.sql

  Inverse normal CDF (probit function) — DuckDB has no built-in for this
  (confirmed by direct testing: erf_inv, norm_inv, inverse_normal_cdf,
  normal_inv, erf, inverse_distribution all fail with "Scalar Function
  ... does not exist"). Required by mart_cfb_preseason_quality.sql to
  convert rank-based percentiles into standardized (z-score) units, per
  design v5's correction: a naive percentile_rank()-based CDF conversion
  allows exact 0/1 percentiles, producing infinite z-values at the
  extremes. This macro is fed p = (rank - 0.5) / n instead, which never
  reaches exactly 0 or 1.

  Implementation: Peter Acklam's rational approximation, a standard,
  widely-used closed-form approximation for the inverse normal CDF.
  Verified directly before use: implemented in Python first, checked
  against Python's exact statistics.NormalDist().inv_cdf() across 11
  test points spanning p=0.001 to p=0.999 (max absolute error 1.58e-09),
  then ported to this exact SQL form and re-verified against the same
  ground truth with the same result — confirming no translation error
  was introduced going from Python to SQL.

  Valid for p strictly in (0, 1). Not defined at exactly 0 or 1 (by
  design — see above).
#}

{% macro inv_normal_cdf(p) %}
    CASE
        WHEN {{ p }} < 0.02425 THEN
            (((((-7.784894002430293e-03*sqrt(-2*ln({{ p }}))+(-3.223964580411365e-01))*sqrt(-2*ln({{ p }}))+(-2.400758277161838e+00))*sqrt(-2*ln({{ p }}))+(-2.549732539343734e+00))*sqrt(-2*ln({{ p }}))+4.374664141464968e+00)*sqrt(-2*ln({{ p }}))+2.938163982698783e+00)
            / ((((7.784695709041462e-03*sqrt(-2*ln({{ p }}))+3.224671290700398e-01)*sqrt(-2*ln({{ p }}))+2.445134137142996e+00)*sqrt(-2*ln({{ p }}))+3.754408661907416e+00)*sqrt(-2*ln({{ p }}))+1)
        WHEN {{ p }} <= 0.97575 THEN
            (((((-3.969683028665376e+01*({{ p }}-0.5)*({{ p }}-0.5)+2.209460984245205e+02)*({{ p }}-0.5)*({{ p }}-0.5)+(-2.759285104469687e+02))*({{ p }}-0.5)*({{ p }}-0.5)+1.383577518672690e+02)*({{ p }}-0.5)*({{ p }}-0.5)+(-3.066479806614716e+01))*({{ p }}-0.5)*({{ p }}-0.5)+2.506628277459239e+00) * ({{ p }}-0.5)
            / (((((-5.447609879822406e+01*({{ p }}-0.5)*({{ p }}-0.5)+1.615858368580409e+02)*({{ p }}-0.5)*({{ p }}-0.5)+(-1.556989798598866e+02))*({{ p }}-0.5)*({{ p }}-0.5)+6.680131188771972e+01)*({{ p }}-0.5)*({{ p }}-0.5)+(-1.328068155288572e+01))*({{ p }}-0.5)*({{ p }}-0.5)+1)
        ELSE
            -(((((-7.784894002430293e-03*sqrt(-2*ln(1-{{ p }}))+(-3.223964580411365e-01))*sqrt(-2*ln(1-{{ p }}))+(-2.400758277161838e+00))*sqrt(-2*ln(1-{{ p }}))+(-2.549732539343734e+00))*sqrt(-2*ln(1-{{ p }}))+4.374664141464968e+00)*sqrt(-2*ln(1-{{ p }}))+2.938163982698783e+00)
            / ((((7.784695709041462e-03*sqrt(-2*ln(1-{{ p }}))+3.224671290700398e-01)*sqrt(-2*ln(1-{{ p }}))+2.445134137142996e+00)*sqrt(-2*ln(1-{{ p }}))+3.754408661907416e+00)*sqrt(-2*ln(1-{{ p }}))+1)
    END
{% endmacro %}
