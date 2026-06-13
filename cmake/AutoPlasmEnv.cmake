function(autoplasm_python_env out_var)
  set(${out_var}
      "${CMAKE_COMMAND};-E;env;PYTHONPATH=${CMAKE_SOURCE_DIR}/src"
      PARENT_SCOPE)
endfunction()
