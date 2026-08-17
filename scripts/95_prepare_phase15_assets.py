from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("prepare_phase15_assets_main", module_name="prta_cxr.phase15_assets")
    )
