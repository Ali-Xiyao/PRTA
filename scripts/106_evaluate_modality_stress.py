from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("modality_stress_main", module_name="prta_cxr.modality_stress")
    )
