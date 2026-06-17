# Tools Audit — Houdini MCP (supercharged fork)

Static audit of all bridge tools against the Houdini 21.0 / current HOM API.
Generated during the supercharge pass; updated after a live test session
against a headless `hython` instance (3 additional crash bugs found & fixed).

## Legend
| Status | Meaning |
|--------|---------|
| **ok** | Verified clean; no known API issues |
| **fixed** | Was broken; patched in this fork |
| **gated** | Executes but crashes Houdini MCP; now requires `allow_dangerous=True` |
| **new** | Added in this fork |

---

## Root-cause bugs fixed globally

| Bug | Location(s) | Fix |
|-----|-------------|-----|
| `list(node.color())` — `Color` not iterable | `handlers/nodes.py:82` | → `node.color().rgb()` |
| `parm.label()` — no `.label()` on `hou.Parm` | `handlers/nodes.py:96`, `handlers/context.py:61`, `handlers/parameters.py:16,69` | → `parm.parmTemplate().label()` |
| `search_docs` / `get_doc` — offline BM25 index never built | `houdini_rag.py` | → on-demand proxy via `houdini_docs.py` |

---

## Live-test crash bugs fixed (headless `hython` session)

| Bug | Location | Symptom | Fix |
|-----|----------|---------|-----|
| `hou.parmTemplateType.Ordinal` — enum member does not exist in H21 | `handlers/nodes.py` (`get_node_info`) | `type object 'parmTemplateType' has no attribute 'Ordinal'` | dropped the enum; `_menu_label()` now detects menus via `menuLabels()` and handles both int-indexed and string-token menus |
| `geo.vertices()` — `Geometry` has no such method | `handlers/geometry.py` (`get_geo_summary`, x2) | `'Geometry' object has no attribute 'vertices'` | → `geo.intrinsicValue("vertexcount")` (also faster) |
| `hou.text.vexSyntaxCheck` — API does not exist | `handlers/vex.py` (`validate_vex`) | `'text' object has no attribute 'vexSyntaxCheck'` | compile snippet in a throwaway wrangle, read `wr.errors()` |

---

## Tool table (168 tools)

| Tool | Status | Notes |
|------|--------|-------|
| `ping` | ok | |
| `get_connection_status` | ok | |
| `get_scene_info` | ok | |
| `create_node` | ok | |
| `execute_houdini_code` | ok | |
| `render_single_view` | **gated** | Crashes MCP (WinError 10054). Requires `allow_dangerous=True` |
| `render_quad_views` | **gated** | Crashes MCP (WinError 10054). Requires `allow_dangerous=True` |
| `render_specific_camera` | **gated** | Crashes MCP (WinError 10054). Requires `allow_dangerous=True` |
| `modify_node` | ok | |
| `delete_node` | ok | |
| `get_node_info` | **fixed** | Color bug; label bug; 20-parm cap; now shows changed-only parms + `type_label` |
| `set_material` | ok | |
| `connect_nodes` | ok | |
| `disconnect_node_input` | ok | |
| `set_node_flags` | ok | |
| `save_scene` | ok | |
| `load_scene` | ok | |
| `set_expression` | ok | |
| `set_frame` | ok | |
| `get_geo_summary` | **fixed** | `geo.vertices()` crash → `vertexcount` intrinsic (live-test) |
| `layout_children` | ok | |
| `set_node_color` | ok | |
| `find_error_nodes` | ok | |
| `get_network_overview` | ok | |
| `get_cook_chain` | ok | |
| `explain_node` | **fixed** | `parm.label()` → `parm.parmTemplate().label()` |
| `get_scene_summary` | ok | |
| `get_selection` | ok | |
| `set_selection` | ok | |
| `get_parameter` | **fixed** | `parm.label()` → `parm.parmTemplate().label()` |
| `set_parameter` | ok | |
| `set_parameters` | ok | |
| `get_parameter_schema` | **fixed** | `parm.label()` → `template.label()` |
| `get_expression` | ok | |
| `revert_parameter` | ok | |
| `link_parameters` | ok | |
| `lock_parameter` | ok | |
| `create_spare_parameter` | ok | |
| `create_spare_parameters` | ok | |
| `set_keyframe` | ok | |
| `set_keyframes` | ok | |
| `delete_keyframe` | ok | |
| `get_keyframes` | ok | |
| `get_frame` | ok | |
| `set_frame_range` | ok | |
| `set_playback_range` | ok | |
| `playbar_control` | ok | |
| `create_wrangle` | ok | |
| `set_wrangle_code` | ok | |
| `get_wrangle_code` | ok | |
| `create_vex_expression` | ok | |
| `validate_vex` | **fixed** | `hou.text.vexSyntaxCheck` crash → throwaway-wrangle cook + `errors()` (live-test) |
| `list_materials` | ok | |
| `get_material_info` | ok | |
| `create_material_network` | ok | |
| `assign_material` | ok | |
| `list_material_types` | ok | |
| `copy_node` | ok | |
| `move_node` | ok | |
| `rename_node` | ok | |
| `list_children` | ok | |
| `find_nodes` | ok | |
| `list_node_types` | ok | |
| `connect_nodes_batch` | ok | |
| `reorder_inputs` | ok | |
| `get_points` | ok | |
| `get_prims` | ok | |
| `get_attrib_values` | ok | |
| `set_detail_attrib` | ok | |
| `get_groups` | ok | |
| `get_group_members` | ok | |
| `get_bounding_box` | ok | |
| `get_prim_intrinsics` | ok | |
| `find_nearest_point` | ok | |
| `execute_hscript` | ok | |
| `evaluate_expression` | ok | |
| `get_env_variable` | ok | |
| `pdg_cook` | ok | |
| `pdg_status` | ok | |
| `pdg_workitems` | ok | |
| `pdg_dirty` | ok | |
| `pdg_cancel` | ok | |
| `lop_stage_info` | ok | |
| `lop_prim_get` | ok | |
| `lop_prim_search` | ok | |
| `lop_layer_info` | ok | |
| `lop_import` | ok | |
| `hda_list` | ok | |
| `hda_get` | ok | |
| `hda_install` | ok | |
| `hda_create` | ok | |
| `batch` | ok | |
| `geo_export` | ok | |
| `render_flipbook` | **gated** | Crashes MCP (WinError 10054). Requires `allow_dangerous=True` |
| `get_simulation_info` | ok | |
| `list_dop_objects` | ok | |
| `get_dop_object` | ok | |
| `get_dop_field` | ok | |
| `get_dop_relationships` | ok | |
| `step_simulation` | ok | |
| `reset_simulation` | ok | |
| `get_sim_memory_usage` | ok | |
| `list_panes` | ok | |
| `get_viewport_info` | ok | |
| `set_viewport_camera` | ok | |
| `set_viewport_display` | ok | |
| `set_viewport_renderer` | ok | |
| `frame_selection` | ok | |
| `frame_all` | ok | |
| `set_viewport_direction` | ok | |
| `capture_screenshot` | ok | Safe alternative to render tools |
| `set_current_network` | ok | |
| `list_render_nodes` | ok | |
| `get_render_settings` | ok | |
| `set_render_settings` | ok | |
| `create_render_node` | ok | |
| `start_render` | **gated** | Crashes MCP (WinError 10054). Requires `allow_dangerous=True` |
| `get_render_progress` | ok | No Houdini connection needed |
| `get_cop_info` | ok | |
| `get_cop_geometry` | ok | |
| `get_cop_layer` | ok | |
| `create_cop_node` | ok | |
| `set_cop_flags` | ok | |
| `list_cop_node_types` | ok | |
| `get_cop_vdb` | ok | |
| `get_chop_data` | ok | |
| `create_chop_node` | ok | |
| `list_chop_channels` | ok | |
| `export_chop_to_parm` | ok | |
| `list_takes` | ok | |
| `get_current_take` | ok | |
| `set_current_take` | ok | |
| `create_take` | ok | |
| `list_caches` | ok | |
| `get_cache_status` | ok | |
| `clear_cache` | ok | |
| `write_cache` | ok | |
| `list_usd_prims` | ok | |
| `get_usd_attribute` | ok | |
| `set_usd_attribute` | ok | |
| `get_usd_prim_stats` | ok | |
| `get_last_modified_prims` | ok | |
| `create_lop_node` | ok | |
| `get_usd_composition` | ok | |
| `get_usd_variants` | ok | |
| `inspect_usd_layer` | ok | |
| `list_lights` | ok | |
| `setup_pyro_sim` | ok | |
| `setup_rbd_sim` | ok | |
| `setup_flip_sim` | ok | |
| `setup_vellum_sim` | ok | |
| `create_material_workflow` | ok | |
| `assign_material_workflow` | ok | |
| `build_sop_chain` | ok | |
| `setup_render` | ok | |
| `uninstall_hda` | ok | |
| `reload_hda` | ok | |
| `update_hda` | ok | |
| `get_hda_sections` | ok | |
| `get_hda_section_content` | ok | |
| `set_hda_section_content` | ok | |
| `get_houdini_events` | ok | |
| `subscribe_houdini_events` | ok | |
| `search_docs` | **fixed** | Was offline BM25 (index missing). Now on-demand proxy via houdinimd.jchd.me |
| `get_doc` | **fixed** | Same — now fetches live markdown |
| `get_node_doc` | **new** | Resolves scene node → doc path → fetches markdown in one call |
| `get_changed_parms` | **new** | Cheap "what did I tweak" call — only changed parms, no full dump |
| `monitor_render` | ok | No Houdini connection needed |

---

## Summary

| Status | Count |
|--------|-------|
| ok | 153 |
| fixed | 8 |
| gated | 5 |
| new | 2 |
| **Total** | **168** |

> `get_node_info`, `get_geo_summary`, `validate_vex` confirmed working post-fix
> against a live headless `hython` instance. `get_changed_parms`, `get_node_doc`,
> `create_node`/`batch`, `connect_nodes_batch`, `set_parameters`, `set_node_flags`,
> `rename_node`/`move_node`/`delete_node`, `find_nodes`, `get_attrib_values`,
> `create_wrangle`, `find_error_nodes` also exercised live and pass.
