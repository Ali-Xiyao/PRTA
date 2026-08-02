from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("protocol_freeze_main", module_name="prta_cxr.cli_protocol_freeze")
    )
