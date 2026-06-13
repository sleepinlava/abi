function(add_autoplasm_pytest)
  add_test(
    NAME pytest
    COMMAND ${CMAKE_COMMAND} -E env PYTHONPATH=${CMAKE_SOURCE_DIR}/src ${Python3_EXECUTABLE} -m pytest tests
  )
endfunction()
