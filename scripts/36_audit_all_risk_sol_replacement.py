from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "audit_all_risk_sol_replacement_main",
            module_name="prta_cxr.all_risk_sol_replacement",
        )
    )
