if(NOT DEFINED MAMBA_EXE)
  message(FATAL_ERROR "MAMBA_EXE is required")
endif()
if(NOT DEFINED MAMBA_ROOT)
  message(FATAL_ERROR "MAMBA_ROOT is required")
endif()
if(NOT DEFINED ENV_PREFIX)
  message(FATAL_ERROR "ENV_PREFIX is required")
endif()
if(NOT DEFINED ENV_FILE)
  message(FATAL_ERROR "ENV_FILE is required")
endif()

file(MAKE_DIRECTORY "${MAMBA_ROOT}" "${MAMBA_ROOT}/envs" "${MAMBA_ROOT}/pkgs")

if(EXISTS "${ENV_PREFIX}/conda-meta/history")
  message(STATUS "Updating local mamba environment ${ENV_PREFIX}")
  execute_process(
    COMMAND "${CMAKE_COMMAND}" -E env
            "PIP_CACHE_DIR=${MAMBA_ROOT}/pip-cache"
            "PIP_DISABLE_PIP_VERSION_CHECK=1"
            "${MAMBA_EXE}" env update --no-rc -y -r "${MAMBA_ROOT}" -p "${ENV_PREFIX}" --file "${ENV_FILE}"
    RESULT_VARIABLE env_result
  )
else()
  message(STATUS "Creating local mamba environment ${ENV_PREFIX}")
  execute_process(
    COMMAND "${CMAKE_COMMAND}" -E env
            "PIP_CACHE_DIR=${MAMBA_ROOT}/pip-cache"
            "PIP_DISABLE_PIP_VERSION_CHECK=1"
            "${MAMBA_EXE}" create --no-rc -y -r "${MAMBA_ROOT}" -p "${ENV_PREFIX}" -f "${ENV_FILE}"
    RESULT_VARIABLE env_result
  )
endif()

if(NOT env_result EQUAL 0)
  message(FATAL_ERROR "Failed to create or update ${ENV_PREFIX} from ${ENV_FILE}")
endif()
