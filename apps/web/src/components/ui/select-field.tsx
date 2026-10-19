"use client";
import * as Select from "@radix-ui/react-select";
import Icon from "./icon";

type Props = {
  "aria-label": string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
};

/** Accessible listbox with native form participation and consistent portal styling. */
export default function SelectField({
  "aria-label": label,
  value,
  onValueChange,
  options,
  placeholder = "Select an option",
  disabled,
  required,
}: Props) {
  return (
    <Select.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      required={required}
    >
      <Select.Trigger className="select-trigger" aria-label={label}>
        <Select.Value placeholder={placeholder} />
        <Select.Icon asChild>
          <Icon name="chevron-down" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          className="select-menu"
          position="popper"
          sideOffset={6}
          collisionPadding={12}
        >
          <Select.Viewport className="select-options">
            {options.map((option) => (
              <Select.Item
                className="select-option"
                key={option.value}
                value={option.value}
              >
                <Select.ItemText>{option.label}</Select.ItemText>
                <Select.ItemIndicator className="select-check">
                  <Icon name="check" />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
