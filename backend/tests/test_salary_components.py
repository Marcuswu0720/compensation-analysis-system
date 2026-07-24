from app.ingestion.salary_components import extract_salary_components


def test_formal_extraction_matches_real_column_names():
    row = {
        "Actual Monthly Basic Salary": 116470.79,
        "Performance STD": 57058.91,
        "Coefficient": 1.2,
        "Performance Bonus": 65210.18,
        "Commission/Bonus": 1000.0,
        "Overtime Amount": 91690.54,
        "Other Income": 0,
        "Welfare Fund": 0,
        "Call Allowance": 4000,
        "Internet Allowance": 0,
        "Traffic Allowance": 0,
        "Transportation Subsidy": 20000,
        "Total Gross Salary": 298371.51,  # = basic+perf+comm+ot+other exactly here
        "Statutory payments": 18043.07,
        "Monthly Income Tax": 33564.95,
        "Other Deduction": 0,
        "Private Loan": 0,
        "Bank Charge": 53.75,
        "Total Net Pay": 250075.47,
    }
    result = extract_salary_components(row, "formal")

    assert result["basic_salary_actual"] == 116470.79
    assert result["performance_std"] == 57058.91
    assert result["performance_coefficient"] == 1.2
    assert result["performance_bonus"] == 65210.18
    assert result["commission_bonus"] == 1000.0
    assert result["overtime_amount"] == 91690.54
    assert result["other_income"] == 24000.0  # 0+0+4000+0+0+20000
    assert result["gross_salary"] == 298371.51
    assert result["employer_statutory_cost"] == 18043.07
    assert result["deduction_total"] == 33564.95 + 0 + 0 + 53.75
    assert result["net_pay"] == 250075.47
    assert result["gross_salary_component_mismatch"] is False
    # Internal-only deduction sub-fields must not leak into the stored result.
    assert "monthly_income_tax" not in result
    assert "bank_charge" not in result


def test_contract_extraction_uses_different_column_names_and_sums_statutory():
    row = {
        "Actual Monthly Basic Salary": 200000.0,
        "Performance Standard": 50000.0,
        "KPI Coeff.": 1.0,
        "Perfomance bonus": 50000.0,  # sic - real source column is misspelled
        "Commission/Bonus": 0.0,
        "Overtime income": 5000.0,
        "Arrears/Other Income": 2000.0,
        "Actual Gross Total Amount": 257000.0,
        "NSITF": 1000.0,
        "Pension ER": 2000.0,
        "ITF": 500.0,
        "HMO": 1500.0,
        "Monthly Income Tax": 10000.0,
        "Other Deduction": 0.0,
        "Bank Charges": 100.0,
        "Net Amount Due": 240000.0,
    }
    result = extract_salary_components(row, "contract")

    assert result["basic_salary_actual"] == 200000.0
    assert result["performance_std"] == 50000.0
    assert result["performance_coefficient"] == 1.0
    assert result["performance_bonus"] == 50000.0
    assert result["overtime_amount"] == 5000.0
    assert result["other_income"] == 2000.0
    assert result["gross_salary"] == 257000.0
    assert result["employer_statutory_cost"] == 1000.0 + 2000.0 + 500.0 + 1500.0  # NSITF+PensionER+ITF+HMO
    assert result["deduction_total"] == 10000.0 + 0.0 + 100.0  # no private_loan for contract
    assert result["net_pay"] == 240000.0
    assert result["gross_salary_component_mismatch"] is False


def test_mismatch_flag_set_when_gross_salary_does_not_equal_component_sum():
    row = {
        "Actual Monthly Basic Salary": 100000.0,
        "Performance Bonus": 0.0,
        "Commission/Bonus": 0.0,
        "Overtime Amount": 0.0,
        "Total Gross Salary": 999999.0,  # deliberately doesn't match the components
        "Statutory payments": 0.0,
    }
    result = extract_salary_components(row, "formal")
    assert result["gross_salary_component_mismatch"] is True


def test_missing_columns_default_to_zero_not_crash():
    result = extract_salary_components({}, "formal")
    assert result["basic_salary_actual"] == 0.0
    assert result["gross_salary"] == 0.0
    assert result["gross_salary_component_mismatch"] is False  # 0 == 0
