from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("tracin_audit_main", module_name="prta_cxr.cli_tracin_audit")
    )
