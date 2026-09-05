import React from 'react'

type SortButtonProps = {
  label: string
  active: boolean
  direction: 'asc' | 'desc'
  title?: string
  onClick: () => void
}

/** Clickable table-header sort control. */
export function SortHeaderButton({ label, active, direction, title, onClick }: SortButtonProps) {
  const marker = active ? (direction === 'asc' ? ' ↑' : ' ↓') : ''
  return (
    <button
      type="button"
      className={`th-sort${active ? ' is-active' : ''}`}
      title={title || `Sort by ${label}`}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
    >
      {label}
      <span className="th-sort-marker" aria-hidden="true">
        {marker || ' ↕'}
      </span>
    </button>
  )
}

type HeaderSelectProps = {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  title?: string
}

/** Compact filter select nested under a column header. */
export function HeaderFilterSelect({ label, value, options, onChange, title }: HeaderSelectProps) {
  return (
    <div className="th-stack" title={title}>
      <span className="th-label">{label}</span>
      <select
        className="th-filter-select"
        value={value}
        aria-label={`Filter ${label}`}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

type HeaderNumberFilterProps = {
  label: string
  value: string
  placeholder?: string
  title?: string
  min?: number
  max?: number
  step?: number
  sortActive?: boolean
  sortDirection?: 'asc' | 'desc'
  onSort?: () => void
  onChange: (value: string) => void
}

/** Sortable header with an optional numeric min filter. */
export function HeaderSortFilter({
  label,
  value,
  placeholder = 'Min',
  title,
  min,
  max,
  step,
  sortActive,
  sortDirection = 'desc',
  onSort,
  onChange,
}: HeaderNumberFilterProps) {
  return (
    <div className="th-stack" title={title}>
      {onSort ? (
        <SortHeaderButton
          label={label}
          active={Boolean(sortActive)}
          direction={sortDirection}
          title={title}
          onClick={onSort}
        />
      ) : (
        <span className="th-label">{label}</span>
      )}
      <input
        className="th-filter-input"
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        placeholder={placeholder}
        aria-label={`Minimum ${label}`}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
