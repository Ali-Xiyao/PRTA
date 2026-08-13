from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("main", module_name="prta_cxr.data.hard_cmcp_cli")
    )
