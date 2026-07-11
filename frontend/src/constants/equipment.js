// Equipment option lists shared by the customer form and the installation-page
// inventory panel, so the makes / capacities / watts stay in sync everywhere.

export const INVERTER_OPTIONS = [
  { label: 'UTL',     value: 'UTL',     warranty: '10 YEAR' },
  { label: 'WAAREE',  value: 'WAAREE',  warranty: '10 YEAR' },
  { label: 'APS',     value: 'APS',     warranty: '10 YEAR' },
  { label: 'KSOLARE', value: 'KSOLARE', warranty: '10 YEAR' },
  { label: 'GOODWE',  value: 'GOODWE',  warranty: '10 YEAR' },
  { label: 'Xwatt',   value: 'Xwatt',   warranty: '10 YEAR' },
  { label: 'Polycab', value: 'Polycab', warranty: '8 YEAR'  },
  { label: 'Microtek Inverter', value: 'Microtek Inverter', warranty: '10 YEAR' },
  { label: 'Pv blink', value: 'Pv blink', warranty: '10 YEAR' },
]

export const PANEL_OPTIONS = [
  { label: 'UTL',     value: 'UTL',     warranty: '27 YEAR' },
  { label: 'ADANI',   value: 'ADANI',   warranty: '30 YEAR' },
  { label: 'WAAREE',  value: 'WAAREE',  warranty: '30 YEAR' },
  { label: 'TATA',    value: 'TATA',    warranty: '30 YEAR' },
  { label: 'PREMIER', value: 'PREMIER', warranty: '30 YEAR' },
  { label: 'APS',     value: 'APS',     warranty: '30 YEAR' },
]

export const PANEL_WATT_OPTIONS = [
  '500', '525', '530', '540', '545', '550',
  '570', '575', '580', '585', '590', '600',
  '610', '615', '620',
]

export const INVERTER_CAPACITY_OPTIONS = [
  '1 kW', '2 kW', '3 kW', '3.3 kW', '3.6 kW', '4 kW', '4.6 kW',
  '5 kW', '5.5 kW', '6 kW', '8 kW', '10 kW', '12 kW', '15 kW', '20 kW',
]
