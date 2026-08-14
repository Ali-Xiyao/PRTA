from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "launch_wave047_local_lane_main",
            module_name="prta_cxr.wave047_resource_amendment",
        )
    )
