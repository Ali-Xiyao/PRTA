from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "audit_sol_label_replacement_main",
            module_name="prta_cxr.sol_label_replacement",
        )
    )
