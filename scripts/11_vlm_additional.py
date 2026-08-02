from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("vlm_additional_main", module_name="prta_cxr.cli_vlm")
    )
