cmake_minimum_required(VERSION 3.18)

project(AutoPlasm VERSION 0.1.0 LANGUAGES NONE)

set(AUTOPLASM_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_minimal.yaml" CACHE FILEPATH "AutoPlasm config file")
set(AUTOPLASM_ASSEMBLY_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_assembly_full_run.yaml" CACHE FILEPATH "AutoPlasm assembly full-run config file")
set(AUTOPLASM_ILLUMINA_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_illumina_smoke.yaml" CACHE FILEPATH "AutoPlasm Illumina short-read smoke config file")
set(AUTOPLASM_ONT_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_ont_smoke.yaml" CACHE FILEPATH "AutoPlasm ONT long-read smoke config file")
set(AUTOPLASM_HIFI_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_hifi_smoke.yaml" CACHE FILEPATH "AutoPlasm PacBio HiFi smoke config file")
set(AUTOPLASM_HYBRID_CONFIG "${CMAKE_SOURCE_DIR}/examples/config_hybrid_smoke.yaml" CACHE FILEPATH "AutoPlasm hybrid short+long smoke config file")
set(AUTOPLASM_PROFILE "dry_run" CACHE STRING "AutoPlasm profile")

set(_AUTOPLASM_PYTHON_HINTS)
if(DEFINED ENV{CONDA_PREFIX})
  list(APPEND _AUTOPLASM_PYTHON_HINTS "$ENV{CONDA_PREFIX}/bin")
endif()
list(APPEND _AUTOPLASM_PYTHON_HINTS
  "${CMAKE_SOURCE_DIR}/.mamba/envs/autoplasm-base/bin"
  "$ENV{HOME}/miniforge3/bin"
  "$ENV{HOME}/mambaforge/bin"
  "$ENV{HOME}/micromamba/bin"
  "$ENV{HOME}/miniconda3/bin"
)
find_program(DEFAULT_AUTOPLASM_PYTHON NAMES python python3 HINTS ${_AUTOPLASM_PYTHON_HINTS} REQUIRED)
set(AUTOPLASM_PYTHON "${DEFAULT_AUTOPLASM_PYTHON}" CACHE FILEPATH "Python interpreter for AutoPlasm")
find_program(MAMBA_EXE NAMES micromamba mamba HINTS "${CMAKE_SOURCE_DIR}/.mamba/bin")
find_program(CONDA_LOCK_EXE NAMES conda-lock)
set(AUTOPLASM_MAMBA_ROOT "${CMAKE_SOURCE_DIR}/.mamba" CACHE PATH "Repository-local mamba root")

set(AUTOPLASM_ENV
    "${CMAKE_COMMAND}" "-E" "env"
    "PYTHONPATH=${CMAKE_SOURCE_DIR}/src"
)

add_custom_target(configure_autoplasm
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli list-tools
          --config ${AUTOPLASM_CONFIG}
          --profile ${AUTOPLASM_PROFILE}
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Checking AutoPlasm configuration and registry"
)

if(MAMBA_EXE)
  add_custom_target(check_mamba
    COMMAND ${MAMBA_EXE} --version
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Checking mamba or micromamba"
  )
  add_custom_target(create_envs
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-base
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/base.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-qc
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/qc.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-assembly
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/assembly.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-plasmid-detect
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/plasmid_detect.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-plasmid-binning
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/plasmid_binning.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-annotation
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/annotation.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-integronfinder
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/integronfinder.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-abundance
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/abundance.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-stats
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/stats.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-visualization
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/visualization.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    COMMAND ${CMAKE_COMMAND}
            -D MAMBA_EXE=${MAMBA_EXE}
            -D MAMBA_ROOT=${AUTOPLASM_MAMBA_ROOT}
            -D ENV_PREFIX=${AUTOPLASM_MAMBA_ROOT}/envs/autoplasm-nextflow
            -D ENV_FILE=${CMAKE_SOURCE_DIR}/envs/nextflow.yml
            -P ${CMAKE_SOURCE_DIR}/cmake/CreateLocalEnv.cmake
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Creating or updating repository-local AutoPlasm mamba environments"
  )
else()
  add_custom_target(check_mamba
    COMMAND ${CMAKE_COMMAND} -E echo "mamba or micromamba was not found."
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
  add_custom_target(create_envs
    COMMAND ${CMAKE_COMMAND} -E echo "mamba or micromamba was not found; install it before creating environments."
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()

if(CONDA_LOCK_EXE)
  add_custom_target(lock_envs
    COMMAND ${CONDA_LOCK_EXE} -f ${CMAKE_SOURCE_DIR}/envs/base.yml -p linux-64
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    COMMENT "Locking AutoPlasm conda environment"
  )
else()
  add_custom_target(lock_envs
    COMMAND ${CMAKE_COMMAND} -E echo "conda-lock was not found; install it to generate conda-lock.yml."
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  )
endif()

add_custom_target(check_tools
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli check-tools
          --config ${AUTOPLASM_CONFIG}
          --profile ${AUTOPLASM_PROFILE}
          --dry-run
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Checking registered bioinformatics tools"
)

add_custom_target(fetch_examples
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli fetch-examples
          --dataset plasmid_refseq_smoke
          --outdir ${CMAKE_SOURCE_DIR}/data/examples/plasmid_refseq_smoke
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Fetching AutoPlasm public assembly smoke dataset"
)

add_custom_target(setup_resources
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli setup-resources
          --config ${AUTOPLASM_ASSEMBLY_CONFIG}
          --profile local
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Preparing lightweight AutoPlasm core databases"
)

add_custom_target(run_assembly_smoke
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli run
          --config ${AUTOPLASM_ASSEMBLY_CONFIG}
          --profile local
          --outdir ${CMAKE_SOURCE_DIR}/results/assembly_full_run
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm assembly-only full smoke workflow"
)

add_custom_target(run_illumina_smoke_dry
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_ILLUMINA_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_SOURCE_DIR}/results/illumina_smoke_dry
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm Illumina short-read smoke dry-run workflow"
)

add_custom_target(run_ont_smoke_dry
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_ONT_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_SOURCE_DIR}/results/ont_smoke_dry
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm ONT long-read smoke dry-run workflow"
)

add_custom_target(run_hifi_smoke_dry
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_HIFI_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_SOURCE_DIR}/results/hifi_smoke_dry
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm PacBio HiFi smoke dry-run workflow"
)

add_custom_target(run_hybrid_smoke_dry
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_HYBRID_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_SOURCE_DIR}/results/hybrid_smoke_dry
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm hybrid short+long smoke dry-run workflow"
)

enable_testing()
add_test(
  NAME pytest
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m pytest ${CMAKE_SOURCE_DIR}/tests
)
add_test(
  NAME autoplasm_help
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli --help
)
add_test(
  NAME ruff
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m ruff check
          ${CMAKE_SOURCE_DIR}/src ${CMAKE_SOURCE_DIR}/tests
)
add_test(
  NAME black_src
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m black --check
          ${CMAKE_SOURCE_DIR}/src
)
add_test(
  NAME black_tests
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m black --check
          ${CMAKE_SOURCE_DIR}/tests
)
add_test(
  NAME mypy
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m mypy
          ${CMAKE_SOURCE_DIR}/src
)
add_test(
  NAME autoplasm_dry_run
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${CMAKE_SOURCE_DIR}/examples/config_minimal.yaml
          --profile dry_run
          --outdir ${CMAKE_BINARY_DIR}/autoplasm_dry_run
)
add_test(
  NAME autoplasm_illumina_dry_run
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_ILLUMINA_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_BINARY_DIR}/autoplasm_illumina_dry_run
)
add_test(
  NAME autoplasm_ont_dry_run
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_ONT_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_BINARY_DIR}/autoplasm_ont_dry_run
)
add_test(
  NAME autoplasm_hifi_dry_run
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_HIFI_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_BINARY_DIR}/autoplasm_hifi_dry_run
)
add_test(
  NAME autoplasm_hybrid_dry_run
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_HYBRID_CONFIG}
          --profile dry_run
          --outdir ${CMAKE_BINARY_DIR}/autoplasm_hybrid_dry_run
)
set_tests_properties(
  pytest
  autoplasm_help
  ruff
  black_src
  black_tests
  mypy
  autoplasm_dry_run
  autoplasm_illumina_dry_run
  autoplasm_ont_dry_run
  autoplasm_hifi_dry_run
  autoplasm_hybrid_dry_run
  PROPERTIES
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  TIMEOUT 120
)

add_custom_target(run_tests
  COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
  WORKING_DIRECTORY ${CMAKE_BINARY_DIR}
  COMMENT "Running AutoPlasm tests through CTest"
)

add_custom_target(run_pipeline
  COMMAND ${AUTOPLASM_ENV} ${AUTOPLASM_PYTHON} -m abi.autoplasm.cli dry-run
          --config ${AUTOPLASM_CONFIG}
          --profile ${AUTOPLASM_PROFILE}
          --outdir ${CMAKE_SOURCE_DIR}/results/autoplasm_project
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
  COMMENT "Running AutoPlasm dry-run pipeline"
)
