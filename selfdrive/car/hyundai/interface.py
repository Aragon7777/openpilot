#!/usr/bin/env python3
from cereal import car
from panda import Panda
from common.conversions import Conversions as CV
from common.params import Params
from selfdrive.car.hyundai.values import HyundaiFlags, CAR, DBC, CANFD_CAR, CAMERA_SCC_CAR, EV_CAR, HYBRID_CAR, LEGACY_SAFETY_MODE_CAR, Buttons, CarControllerParams
from selfdrive.car.hyundai.radar_interface import RADAR_START_ADDR
from selfdrive.car import STD_CARGO_KG, create_button_event, scale_rot_inertia, scale_tire_stiffness, gen_empty_fingerprint, get_safety_config
from selfdrive.car.interfaces import CarInterfaceBase
from selfdrive.car.disable_ecu import disable_ecu

ButtonType = car.CarState.ButtonEvent.Type
EventName = car.CarEvent.EventName
ENABLE_BUTTONS = (Buttons.RES_ACCEL, Buttons.SET_DECEL, Buttons.CANCEL)
BUTTONS_DICT = {Buttons.RES_ACCEL: ButtonType.accelCruise, Buttons.SET_DECEL: ButtonType.decelCruise,
                Buttons.GAP_DIST: ButtonType.gapAdjustCruise, Buttons.CANCEL: ButtonType.cancel}


class CarInterface(CarInterfaceBase):
  @staticmethod
  def get_pid_accel_limits(CP, current_speed, cruise_speed):
    return CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), car_fw=[], disable_radar=False):  # pylint: disable=dangerous-default-value
    ret = CarInterfaceBase.get_std_params(candidate, fingerprint)

    ret.carName = "hyundai"
    ret.radarOffCan = RADAR_START_ADDR not in fingerprint[1] or DBC[ret.carFingerprint]["radar"] is None

    # WARNING: disabling radar also disables AEB (and we show the same warning on the instrument cluster as if you manually disabled AEB)
    ret.openpilotLongitudinalControl = disable_radar and (candidate not in (LEGACY_SAFETY_MODE_CAR | CAMERA_SCC_CAR))

    ret.pcmCruise = not ret.openpilotLongitudinalControl

    # These cars have been put into dashcam only due to both a lack of users and test coverage.
    # These cars likely still work fine. Once a user confirms each car works and a test route is
    # added to selfdrive/car/tests/routes.py, we can remove it from this list.
    ret.dashcamOnly = candidate in {CAR.KIA_OPTIMA_H, CAR.ELANTRA_GT_I30}

    ret.steerActuatorDelay = 0.1  # Default delay
    ret.steerLimitTimer = 0.4
    tire_stiffness_factor = 1.

    # exp tuning
    ret.stoppingControl = True
    ret.startingState = True
    ret.vEgoStopping = 0.3  # 1.0, 0.5
    ret.vEgoStarting = 0.8 # needs to be >= vEgoStopping to avoid state jerking the vehicle
    ret.stoppingDecelRate = 0.3
    ret.stopAccel = -2.0
    ret.startAccel = 2.0

    # exp tuning
    ret.longitudinalTuning.kpBP = [0., 5., 35.]
    ret.longitudinalTuning.kpV = [1.2, 0.8, 0.5]
    ret.longitudinalTuning.kiBP = [0., 35.]
    ret.longitudinalTuning.kiV = [0.09, 0.06]

    ret.longitudinalActuatorDelayLowerBound = 0.5  # s
    ret.longitudinalActuatorDelayUpperBound = 0.5  # s
    if candidate in (CAR.SANTA_FE, CAR.SANTA_FE_2022, CAR.SANTA_FE_HEV_2022, CAR.SANTA_FE_PHEV_2022):
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 3982. * CV.LB_TO_KG + STD_CARGO_KG
      ret.wheelbase = 2.766
      # Values from optimizer
      ret.steerRatio = 16.55  # 13.8 is spec end-to-end
      tire_stiffness_factor = 0.82
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[9., 22.], [9., 22.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.2, 0.35], [0.05, 0.09]]
    elif candidate in (CAR.SONATA, CAR.SONATA_HYBRID):
      ret.mass = 1513. + STD_CARGO_KG
      ret.wheelbase = 2.84
      ret.steerRatio = 12.35
      tire_stiffness_factor = 0.65
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.SONATA_LF:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 4497. * CV.LB_TO_KG
      ret.wheelbase = 2.804
      ret.steerRatio = 13.27 * 1.15   # 15% higher at the center seems reasonable
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.PALISADE:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 1999. + STD_CARGO_KG
      ret.wheelbase = 2.90
      ret.steerRatio = 15.6 * 1.15
      tire_stiffness_factor = 0.63
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate in (CAR.ELANTRA, CAR.ELANTRA_GT_I30):
      ret.lateralTuning.pid.kf = 0.00006
      ret.mass = 1275. + STD_CARGO_KG
      ret.wheelbase = 2.7
      ret.steerRatio = 15.4            # 14 is Stock | Settled Params Learner values are steerRatio: 15.401566348670535
      tire_stiffness_factor = 0.385    # stiffnessFactor settled on 1.0081302973865127
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
      ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate == CAR.ELANTRA_2021:
      ret.mass = (2800. * CV.LB_TO_KG) + STD_CARGO_KG
      ret.wheelbase = 2.72
      ret.steerRatio = 12.9
      tire_stiffness_factor = 0.65
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate == CAR.ELANTRA_HEV_2021:
      ret.mass = (3017. * CV.LB_TO_KG) + STD_CARGO_KG
      ret.wheelbase = 2.72
      ret.steerRatio = 12.9
      tire_stiffness_factor = 0.65
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate == CAR.HYUNDAI_GENESIS:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 2060. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.steerRatio = 16.5
      ret.lateralTuning.init('indi')
      ret.lateralTuning.indi.innerLoopGainBP = [0.]
      ret.lateralTuning.indi.innerLoopGainV = [3.5]
      ret.lateralTuning.indi.outerLoopGainBP = [0.]
      ret.lateralTuning.indi.outerLoopGainV = [2.0]
      ret.lateralTuning.indi.timeConstantBP = [0.]
      ret.lateralTuning.indi.timeConstantV = [1.4]
      ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
      ret.lateralTuning.indi.actuatorEffectivenessV = [2.3]
      ret.minSteerSpeed = 60 * CV.KPH_TO_MS
    elif candidate in (CAR.KONA, CAR.KONA_EV, CAR.KONA_HEV, CAR.KONA_EV_2022):
      ret.mass = {CAR.KONA_EV: 1685., CAR.KONA_HEV: 1425., CAR.KONA_EV_2022: 1743.}.get(candidate, 1275.) + STD_CARGO_KG
      ret.wheelbase = 2.6
      ret.steerRatio = 13.42  # Spec
      tire_stiffness_factor = 0.385
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate in (CAR.IONIQ, CAR.IONIQ_EV_LTD, CAR.IONIQ_EV_2020, CAR.IONIQ_PHEV, CAR.IONIQ_HEV_2022):
      ret.lateralTuning.pid.kf = 0.00006
      ret.mass = 1490. + STD_CARGO_KG  # weight per hyundai site https://www.hyundaiusa.com/ioniq-electric/specifications.aspx
      ret.wheelbase = 2.7
      ret.steerRatio = 13.73  # Spec
      tire_stiffness_factor = 0.385
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
      if candidate not in (CAR.IONIQ_EV_2020, CAR.IONIQ_PHEV, CAR.IONIQ_HEV_2022):
        ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate == CAR.IONIQ_PHEV_2019:
      ret.mass = 1550. + STD_CARGO_KG  # weight per hyundai site https://www.hyundaiusa.com/us/en/vehicles/2019-ioniq-plug-in-hybrid/compare-specs
      ret.wheelbase = 2.7
      ret.steerRatio = 13.73
      ret.lateralTuning.init('indi')
      ret.lateralTuning.indi.innerLoopGainBP = [0.]
      ret.lateralTuning.indi.innerLoopGainV = [2.5]
      ret.lateralTuning.indi.outerLoopGainBP = [0.]
      ret.lateralTuning.indi.outerLoopGainV = [3.5]
      ret.lateralTuning.indi.timeConstantBP = [0.]
      ret.lateralTuning.indi.timeConstantV = [1.4]
      ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
      ret.lateralTuning.indi.actuatorEffectivenessV = [1.8]
      ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate == CAR.VELOSTER:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      ret.steerRatio = 13.75 * 1.15
      tire_stiffness_factor = 0.5
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.TUCSON:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 3520. * CV.LB_TO_KG
      ret.wheelbase = 2.67
      ret.steerRatio = 14.00 * 1.15
      tire_stiffness_factor = 0.385
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.TUCSON_HYBRID_4TH_GEN:
      ret.mass = 1680. + STD_CARGO_KG  # average of all 3 trims
      ret.wheelbase = 2.756
      ret.steerRatio = 16.
      tire_stiffness_factor = 0.385
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

    # Kia
    elif candidate == CAR.KIA_SORENTO:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 1985. + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 14.4 * 1.1   # 10% higher at the center seems reasonable
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate in (CAR.KIA_NIRO_EV, CAR.KIA_NIRO_PHEV, CAR.KIA_NIRO_HEV_2021):
      ret.lateralTuning.pid.kf = 0.00006
      ret.mass = 1737. + STD_CARGO_KG
      ret.wheelbase = 2.7
      ret.steerRatio = 13.9 if CAR.KIA_NIRO_HEV_2021 else 13.73  # Spec
      tire_stiffness_factor = 0.385
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
      if candidate == CAR.KIA_NIRO_PHEV:
        ret.minSteerSpeed = 32 * CV.MPH_TO_MS
    elif candidate == CAR.KIA_SELTOS:
      ret.mass = 1337. + STD_CARGO_KG
      ret.wheelbase = 2.63
      ret.steerRatio = 14.56
      tire_stiffness_factor = 1
      ret.lateralTuning.init('indi')
      ret.lateralTuning.indi.innerLoopGainBP = [0.]
      ret.lateralTuning.indi.innerLoopGainV = [4.]
      ret.lateralTuning.indi.outerLoopGainBP = [0.]
      ret.lateralTuning.indi.outerLoopGainV = [3.]
      ret.lateralTuning.indi.timeConstantBP = [0.]
      ret.lateralTuning.indi.timeConstantV = [1.4]
      ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
      ret.lateralTuning.indi.actuatorEffectivenessV = [1.8]
    elif candidate in (CAR.KIA_OPTIMA, CAR.KIA_OPTIMA_H):
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      ret.steerRatio = 13.75
      tire_stiffness_factor = 0.5
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate == CAR.KIA_STINGER:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 1825. + STD_CARGO_KG
      ret.wheelbase = 2.78
      ret.steerRatio = 14.4 * 1.15   # 15% higher at the center seems reasonable
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.KIA_FORTE:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 3558. * CV.LB_TO_KG
      ret.wheelbase = 2.80
      ret.steerRatio = 13.75
      tire_stiffness_factor = 0.5
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.KIA_CEED:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 1450. + STD_CARGO_KG
      ret.wheelbase = 2.65
      ret.steerRatio = 13.75
      tire_stiffness_factor = 0.5
      ret.lateralTuning.pid.kf = 0.00005
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.KIA_K5_2021:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 3228. * CV.LB_TO_KG
      ret.wheelbase = 2.85
      ret.steerRatio = 13.27  # 2021 Kia K5 Steering Ratio (all trims)
      tire_stiffness_factor = 0.5
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.25], [0.05]]
    elif candidate == CAR.KIA_EV6:
      ret.mass = 2055 + STD_CARGO_KG
      ret.wheelbase = 2.9
      ret.steerRatio = 16.
      tire_stiffness_factor = 0.65
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    elif candidate == CAR.IONIQ_5:
      ret.mass = 2012 + STD_CARGO_KG
      ret.wheelbase = 3.0
      ret.steerRatio = 16.
      tire_stiffness_factor = 0.65
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

    # Genesis
    elif candidate == CAR.GENESIS_G70:
      ret.lateralTuning.init('indi')
      ret.lateralTuning.indi.innerLoopGainBP = [0.]
      ret.lateralTuning.indi.innerLoopGainV = [2.5]
      ret.lateralTuning.indi.outerLoopGainBP = [0.]
      ret.lateralTuning.indi.outerLoopGainV = [3.5]
      ret.lateralTuning.indi.timeConstantBP = [0.]
      ret.lateralTuning.indi.timeConstantV = [1.4]
      ret.lateralTuning.indi.actuatorEffectivenessBP = [0.]
      ret.lateralTuning.indi.actuatorEffectivenessV = [1.8]
      ret.steerActuatorDelay = 0.1
      ret.mass = 1640.0 + STD_CARGO_KG
      ret.wheelbase = 2.84
      ret.steerRatio = 13.56
    elif candidate == CAR.GENESIS_G70_2020:
      ret.lateralTuning.pid.kf = 0.
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.112], [0.004]]
      ret.mass = 3673.0 * CV.LB_TO_KG + STD_CARGO_KG
      ret.wheelbase = 2.83
      ret.steerRatio = 12.9
    elif candidate == CAR.GENESIS_G80:
      ret.lateralTuning.pid.kf = 0.00005
      ret.mass = 2060. + STD_CARGO_KG
      ret.wheelbase = 3.01
      ret.steerRatio = 16.5
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.16], [0.01]]
    elif candidate == CAR.GENESIS_G90:
      ret.mass = 2200
      ret.wheelbase = 3.15
      ret.steerRatio = 12.069
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0.], [0.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.16], [0.01]]

    if Params().get_bool("EnforceTorqueLateral"):
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

    # panda safety config
    if candidate in CANFD_CAR:
      ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.noOutput),
                           get_safety_config(car.CarParams.SafetyModel.hyundaiCanfd)]

      # detect HDA2 with LKAS message
      if 0x50 in fingerprint[6]:
        ret.flags |= HyundaiFlags.CANFD_HDA2.value
        ret.safetyConfigs[1].safetyParam |= Panda.FLAG_HYUNDAI_CANFD_HDA2
      else:
        # non-HDA2
        if 0x1cf not in fingerprint[4]:
          ret.flags |= HyundaiFlags.CANFD_ALT_BUTTONS.value
          ret.safetyConfigs[1].safetyParam |= Panda.FLAG_HYUNDAI_CANFD_ALT_BUTTONS
    else:
      ret.enableBsm = 0x58b in fingerprint[0]

      if candidate in LEGACY_SAFETY_MODE_CAR:
        # these cars require a special panda safety mode due to missing counters and checksums in the messages
        ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.hyundaiLegacy)]
      else:
        ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.hyundai, 0)]

      # set appropriate safety param for gas signal
      if candidate in HYBRID_CAR:
        ret.safetyConfigs[0].safetyParam = 2
      elif candidate in EV_CAR:
        ret.safetyConfigs[0].safetyParam = 1

      if ret.openpilotLongitudinalControl:
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_HYUNDAI_LONG

      if candidate in CAMERA_SCC_CAR:
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_HYUNDAI_CAMERA_SCC

      if 0x391 in fingerprint[0]:
        ret.flags |= HyundaiFlags.SP_CAN_LFA_BTN.value
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_HYUNDAI_LFA_BTN

      enhanced_scc = 0x2AB in fingerprint[0] and ret.openpilotLongitudinalControl and Params().get_bool("EnhancedScc")
      if enhanced_scc:
        ret.flags |= HyundaiFlags.SP_ENHANCED_SCC.value
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_HYUNDAI_ESCC

    ret.centerToFront = ret.wheelbase * 0.4

    # TODO: get actual value, for now starting with reasonable value for
    # civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront,
                                                                         tire_stiffness_factor=tire_stiffness_factor)

    return ret

  @staticmethod
  def init(CP, logcan, sendcan):
    if CP.openpilotLongitudinalControl and not (CP.flags & HyundaiFlags.SP_ENHANCED_SCC):
      disable_ecu(logcan, sendcan, addr=0x7d0, com_cont_req=b'\x28\x83\x01')

  def _update(self, c):
    ret = self.CS.update(self.cp, self.cp_cam)

    ret.madsEnabled = self.CS.madsEnabled
    ret.accEnabled = self.CS.accEnabled
    ret.leftBlinkerOn = self.CS.leftBlinkerOn
    ret.rightBlinkerOn = self.CS.rightBlinkerOn
    ret.belowLaneChangeSpeed = self.CS.belowLaneChangeSpeed

    buttonEvents = []

    if ret.cruiseState.enabled and not self.CS.out.cruiseState.enabled:
      be = car.CarState.ButtonEvent.new_message()
      be.pressed = False
      be.type = ButtonType.setCruise
      buttonEvents.append(be)

    if self.CS.cruise_buttons[-1] != self.CS.prev_cruise_buttons:
      be = car.CarState.ButtonEvent.new_message()
      be.type = ButtonType.unknown
      if self.CS.cruise_buttons[-1] != 0:
        be.pressed = True
        but = self.CS.cruise_buttons[-1]
      else:
        be.pressed = False
        but = self.CS.prev_cruise_buttons
      if but == Buttons.RES_ACCEL:
        be.type = ButtonType.accelCruise
      elif but == Buttons.SET_DECEL:
        be.type = ButtonType.decelCruise
      elif but == Buttons.GAP_DIST:
        be.type = ButtonType.gapAdjustCruise
      elif but == Buttons.CANCEL:
        be.type = ButtonType.cancel
      buttonEvents.append(be)

    # MADS BUTTON
    if self.CS.out.madsEnabled != self.CS.madsEnabled:
      be = car.CarState.ButtonEvent.new_message()
      be.pressed = True
      be.type = ButtonType.altButton1
      buttonEvents.append(be)

    ret.buttonEvents = buttonEvents

    extraGears = []
    if not self.CS.CP.openpilotLongitudinalControl:
      extraGears = [car.CarState.GearShifter.sport, car.CarState.GearShifter.low]

    # On some newer model years, the CANCEL button acts as a pause/resume button based on the PCM state
    # To avoid re-engaging when openpilot cancels, check user engagement intention via buttons
    # Main button also can trigger an engagement on these cars
    allow_enable = any(btn in ENABLE_BUTTONS for btn in self.CS.cruise_buttons) or any(self.CS.main_buttons)
    events = self.create_common_events(ret, extra_gears=extraGears, pcm_enable=False, allow_enable=allow_enable)

    if self.CS.brake_error:
      events.add(EventName.brakeUnavailable)

    # low speed steer alert hysteresis logic (only for cars with steer cut off above 10 m/s)
    if ret.vEgo < (self.CP.minSteerSpeed + 2.) and self.CP.minSteerSpeed > 10.:
      self.low_speed_alert = True
    if ret.vEgo > (self.CP.minSteerSpeed + 4.):
      self.low_speed_alert = False
    if self.low_speed_alert and self.CS.madsEnabled:
      events.add(car.CarEvent.EventName.belowSteerSpeed)

    self.CS.disengageByBrake = self.CS.disengageByBrake or ret.disengageByBrake

    enable_pressed = False
    enable_from_brake = False

    if self.CS.disengageByBrake and not ret.brakePressed and not ret.brakeHoldActive and not ret.parkingBrake and self.CS.madsEnabled:
      enable_pressed = True
      enable_from_brake = True

    if not ret.brakePressed and not ret.brakeHoldActive and not ret.parkingBrake:
      self.CS.disengageByBrake = False
      ret.disengageByBrake = False

    for b in ret.buttonEvents:
      # do enable on both accel and decel buttons
      if b.type in (ButtonType.accelCruise, ButtonType.decelCruise, ButtonType.setCruise) and not b.pressed:
        enable_pressed = True
      # do disable on MADS button if ACC is disabled
      if b.type == ButtonType.altButton1 and b.pressed:
        if not self.CS.madsEnabled: # disabled MADS
          if not ret.cruiseState.enabled:
            events.add(EventName.buttonCancel)
          else:
            events.add(EventName.manualSteeringRequired)
        else: # enabled MADS
          if not ret.cruiseState.enabled:
            enable_pressed = True
      # do disable on button down
      if b.type == ButtonType.cancel and b.pressed:
        if not self.CS.madsEnabled:
          events.add(EventName.buttonCancel)
        elif ret.cruiseState.enabled:
          events.add(EventName.manualLongitudinalRequired)
    if (ret.cruiseState.enabled or self.CS.madsEnabled) and enable_pressed:
      if enable_from_brake:
        events.add(EventName.silentButtonEnable)
      else:
        events.add(EventName.buttonEnable)

    ret.events = events.to_msg()

    return ret

  def apply(self, c):
    return self.CC.update(c, self.CS)
