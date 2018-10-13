ifeq ($(PACKAGE_SET),dom0)
  RPM_SPEC_FILES := rpm_spec/gpg-split-dom0.spec
else ifeq ($(PACKAGE_SET),vm)
  ifneq ($(filter $(DISTRIBUTION), debian qubuntu),)
    DEBIAN_BUILD_DIRS := debian
  endif

  RPM_SPEC_FILES := rpm_spec/gpg-split.spec
  ARCH_BUILD_DIRS := archlinux
endif

# vim: filetype=make
