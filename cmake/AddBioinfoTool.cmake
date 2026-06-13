function(add_bioinfo_tool_check target_name tool_name)
  add_custom_target(${target_name}
    COMMAND ${CMAKE_COMMAND} -E echo "Check ${tool_name} through autoplasm check-tools"
  )
endfunction()
