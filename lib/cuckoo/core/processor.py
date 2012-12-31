# Copyright (C) 2010-2012 Cuckoo Sandbox Developers.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import logging
from distutils.version import StrictVersion

from lib.cuckoo.common.config import Config
from lib.cuckoo.common.objects import LocalDict
from lib.cuckoo.common.constants import CUCKOO_VERSION
from lib.cuckoo.common.exceptions import CuckooProcessingError
from lib.cuckoo.core.plugins import list_plugins

log = logging.getLogger(__name__)

class Processor:
    """Analysis Results Processing Engine.

    This class handles the loading and execution of the processing modules.
    It executes the enabled ones sequentially and generates a dictionary which
    is then passed over the reporting engine.
    """

    def __init__(self, analysis_path):
        """@param analysis_path: analysis folder path."""
        self.analysis_path = analysis_path

    def _run_processing(self, module):
        """Run a processing module.
        @param module: processing module to run.
        @param results: results dict.
        @return: results generated by module.
        """
        # Initialize the specified processing module.
        current = module()
        # Provide it the path to the analysis results.
        current.set_path(self.analysis_path)
        # Load the analysis.conf configuration file.
        current.cfg = Config(current.conf_path)

        # If current processing module is disabled, skip it.
        if not current.enabled:
            return None

        try:
            # Run the processing module and retrieve the generated data to be
            # appended to the general results container.
            data = current.run()

            log.debug("Executed processing module \"%s\" on analysis at \"%s\""
                      % (current.__class__.__name__, self.analysis_path))

            # If succeeded, return they module's key name and the data to be
            # appended to it.
            return {current.key : data}
        except CuckooProcessingError as e:
            log.warning("The processing module \"%s\" returned the following "
                        "error: %s" % (current.__class__.__name__, e))
        except Exception as e:
            log.exception("Failed to run the processing module \"%s\":"
                          % (current.__class__.__name__))

        return None

    def _run_signature(self, signature, results):
        """Run a signature.
        @param signature: signature to run.
        @param signs: signature results dict.
        @return: matched signature.
        """
        # Initialize the current signature.
        current = signature(LocalDict(results))

        log.debug("Running signature \"%s\"" % current.name)

        # If the signature is disabled, skip it.
        if not current.enabled:
            return None

        # Since signatures can hardcode some values or checks that might
        # become obsolete in future versions or that might already be obsolete,
        # I need to match its requirements with the running version of Cuckoo.
        version = CUCKOO_VERSION.split("-")[0]

        # If provided, check the minimum working Cuckoo version for this
        # signature.
        if current.minimum:
            try:
                # If the running Cuckoo is older than the required minimum
                # version, skip this signature.
                if StrictVersion(version) < StrictVersion(current.minimum.split("-")[0]):
                    log.debug("You are running an older incompatible version "
                              "of Cuckoo, the signature \"%s\" requires "
                              "minimum version %s"
                              % (current.name, current.minimum))
                    return None
            except ValueError:
                log.debug("Wrong minor version number in signature %s"
                          % current.name)
                return None

        # If provided, check the maximum working Cuckoo version for this
        # signature.
        if current.maximum:
            try:
                # If the running Cuckoo is newer than the required maximum
                # version, skip this signature.
                if StrictVersion(version) > StrictVersion(current.maximum.split("-")[0]):
                    log.debug("You are running a newer incompatible version "
                              "of Cuckoo, the signature \"%s\" requires "
                              "maximum version %s"
                              % (current.name, current.maximum))
                    return None
            except ValueError:
                log.debug("Wrong major version number in signature %s"
                          % current.name)
                return None

        try:
            # Run the signature and if it gets matched, extract key information
            # from it and append it to the results container.
            if current.run():
                matched = {"name" : current.name,
                           "description" : current.description,
                           "severity" : current.severity,
                           "references" : current.references,
                           "data" : current.data,
                           "alert" : current.alert}

                log.debug("Analysis at \"%s\" matched signature \"%s\""
                          % (self.analysis_path, current.name))

                # Return information on the matched signature.
                return matched
        except Exception as e:
            log.exception("Failed to run signature \"%s\":" % (current.name))

        return None

    def run(self):
        """Run all processing modules and all signatures.
        @return: processing results.
        """
        # This is the results container. It's what will be used by all the
        # reporting modules to make it consumable by humans and machines.
        # It will contain all the results generated by every processing
        # module available. Its structure can be observed throgh the JSON
        # dump in the the analysis' reports folder.
        # We friendly call this "fat dict".
        results = {}

        # Order modules using the user-defined sequence number.
        # If none is specified for the modules, they are selected in
        # alphabetical order.
        modules_list = list_plugins(group="processing")
        modules_list.sort(key=lambda module: module.order)

        # Run every loaded processing module.
        for module in modules_list:
            result = self._run_processing(module)
            # If it provided some results, append it to the big results
            # container.
            if result:
                results.update(result)

        # This will contain all the matched signatures.
        sigs = []

        # Run every loaded signature.
        for signature in list_plugins(group="signatures"):
            match = self._run_signature(signature, results)
            # If the signature is matched, add it to the list.
            if match:
                sigs.append(match)

        # Sort the matched signatures by their severity level.
        sigs.sort(key=lambda key: key["severity"])

        # Append the signatures to the fat dict.
        results["signatures"] = sigs

        # Return the fat dict.
        return results
