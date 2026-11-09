# DSRemoteConnect constants, taken from ConstsAndTypeDefs_Documented.h (DSRemoteConnect 1.1.3.26 docs).


# --- DX_ERROR_CODE: return codes of every dscon* function. ---
# Positive values are informational, 0 is success, negative values are errors.
DSX_TOO_MANY_SAMPLES_AVAILABLE = 2          # More samples available than requested (warning).
DSX_END_OF_ENUM = 1                         # End of enumeration reached.
DSX_NO_ERROR = 0                            # Operation successful.
DSX_DCOM_CHANNEL_ID_NOT_FOUND = -1          # DCOM: Channel ID not found in current setup.
DSX_DCOM_UNKNOWN_ERROR = -2                 # DCOM: Unknown error occurred.
DSX_DCOM_NO_DATA = -3                       # DCOM: No data available for reading.
DSX_DCOM_NOT_CONNECTED = -4                 # DCOM: Not connected to Dewesoft application.
DSX_COUNT_OUT_OF_BOUNDS = -5                # Count parameter out of valid bounds.
DSX_NET_UNABLE_TO_CONNECT = -6              # NET: Unable to establish network connection.
DSX_NET_UNKNOWN_ERROR = -7                  # NET: Unknown network error occurred.
DSX_UNKNOWN_ERROR = -8                      # General unknown error.
DSX_NULL_HANDLER = -9                       # Null handle or pointer passed to function.
DSX_INVALID_CONNECTION_STRING = -10         # Invalid connection string format.
DSX_DCOM_ISSUE = -11                        # DCOM: General DCOM interface issue.
DSX_DCOM_COULD_NOT_CONNECT = -12            # DCOM: Could not establish DCOM connection.
DSX_DCOM_NO_CHANNELS_TO_ENUMERATE = -13     # DCOM: No channels available for enumeration.
DSX_DCOM_EMPTY_ARRAY = -14                  # DCOM: Empty array returned.
DSX_CANNOT_MAKE_CH_INSTANCE = -15           # Cannot create channel instance.
DSX_WRONG_PROPS_NAME = -16                  # Wrong property name specified.
DSX_ERROR_GETTING_LENGTH_PROPS = -17        # Error getting property length.
DSX_NET_COMMAND_NOT_SUPPORTED = -18         # NET: Command not supported by server.
DSX_CH_IS_NOT_CONTROL = -19                 # Channel is not a control channel.
DSX_NET_SETUP_NOT_FOUND = -20               # NET: Setup file not found.
DSX_NET_BUFFER_OVERWRITTEN = -21            # NET: Buffer was overwritten before reading.
DSX_NET_ISACQ_CHECKFAILED = -22             # NET: Acquisition status check failed.
DSX_NET_STOPPING_ACQ_FAILED = -23           # NET: Failed to stop acquisition.
DSX_NET_INITIALIZING_VECTOR_CH = -24        # NET: Error initializing vector channels.
DSX_NET_GETTIMING_FAILED = -25              # NET: Failed to get timing information.
DSX_NET_PREPARECHFORTRANSFER_FAILED = -26   # NET: Failed to prepare channel for transfer.
DSX_NET_STARTTRANSFER_FAILED = -27          # NET: Failed to start data transfer.
DSX_NET_STARTACQ_FAILED = -28               # NET: Failed to start acquisition.

# Return code -> constant name (built here, while only DX_ERROR_CODE names exist).
_RC_NAMES = {v: k for k, v in list(globals().items()) if k.startswith("DSX_")}


def rc_name(rc):
    """Readable name of a dscon* return code, e.g. "failed: %s" % rc_name(rc)."""
    return _RC_NAMES.get(rc, "UNKNOWN_RC(%d)" % rc)


# --- DSX_CONNECTION_TYPE: argument of dsconCreateInstance. ---
DSX_CONNECTION_TYPE_DCOM = 0                # DCOM connection for local/remote Windows applications.
DSX_CONNECTION_TYPE_NET = 1                 # Network connection using TCP/IP.


# --- DSX_CH_TYPE: channel sampling type. ---
DSX_CH_ASYNC = 0                            # Data arrives at irregular intervals.
DSX_CH_SYNC = 1                             # Data sampled at regular intervals.
DSX_CH_SINGLE_VALUE = 2                     # One value per measurement.


# --- DSX_DATA_TYPE: channel data types for DCOM connections. ---
dtByte = 0                                  # 8-bit unsigned byte
dtShortInt = 1                              # 16-bit signed integer
dtSmallInt = 2                              # 16-bit signed integer (alternative)
dtWord = 3                                  # 16-bit unsigned integer
dtInteger = 4                               # 32-bit signed integer
dtSingle = 5                                # 32-bit floating point
dtInt64 = 6                                 # 64-bit signed integer
dtDouble = 7                                # 64-bit floating point
dtLongword = 8                              # 32-bit unsigned integer
dtComplexSingle = 9                         # Complex 32-bit floating point
dtComplexDouble = 10                        # Complex 64-bit floating point
dtText = 11                                 # Text/string data
dtBinary = 12                               # Binary data
dtCANMessage = 13                           # CAN bus message
dtCANFDMessage = 14                         # CAN FD message
dtBytes8 = 15                               # 8-byte data block
dtBytes16 = 16                              # 16-byte data block
dtBytes32 = 17                              # 32-byte data block
dtBytes64 = 18                              # 64-byte data block


# --- DSX_NET_DATA_TYPE: channel data types for NET connections. ---
dtSignedCharNet = 0                         # 8-bit signed character
dtUnSignedCharNet = 1                       # 8-bit unsigned character
dtShortNet = 2                              # 16-bit signed integer
dtUnsignedShortNet = 3                      # 16-bit unsigned integer
dtIntegerNet = 4                            # 32-bit signed integer
dtFloatNet = 5                              # 32-bit floating point
dtLongLongNet = 6                           # 64-bit signed integer
dtDoubleNet = 7                             # 64-bit floating point
dtLongWordNet = 8                           # 32-bit unsigned integer
dtComplexSingleNet = 9                      # Complex 32-bit floating point
dtComplexDoubleNet = 10                     # Complex 64-bit floating point
dtTextNet = 11                              # Text/string data
dtBinaryNet = 12                            # Binary data
dtCANMessageNet = 13                        # CAN bus message
dtCANFDMessageNet = 14                      # CAN FD message
dtBytes8Net = 15                            # 8-byte data block
dtBytes16Net = 16                           # 16-byte data block
dtBytes32Net = 17                           # 32-byte data block
dtBytes64Net = 18                           # 64-byte data block

