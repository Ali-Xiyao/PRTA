from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "phase16_safety_routing_main",
            module_name="prta_cxr.phase16_safety_routing",
        )
    )
