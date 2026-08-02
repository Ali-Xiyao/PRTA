from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("prepare_luna_pilot_main", module_name="prta_cxr.cli_labeling")
    )
