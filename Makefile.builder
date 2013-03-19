ifeq ($(PACKAGE_SET),dom0)
RPM_SPEC_FILES := rpm_spec/gpg-split-dom0.spec
else ifeq ($(PACKAGE_SET),vm)
RPM_SPEC_FILES := rpm_spec/gpg-split.spec
endif
