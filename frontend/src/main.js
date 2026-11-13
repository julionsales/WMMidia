import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import { definePreset } from '@primeuix/themes'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Tooltip from 'primevue/tooltip'

import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import ProgressSpinner from 'primevue/progressspinner'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import ToggleSwitch from 'primevue/toggleswitch'
import DatePicker from 'primevue/datepicker'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'

import 'primeicons/primeicons.css'
import './styles.css'

import App from './App.vue'
import router from './router'
import { ptBR } from './utils/locale'

const Preset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{teal.50}', 100: '{teal.100}', 200: '{teal.200}', 300: '{teal.300}', 400: '{teal.400}',
      500: '{teal.500}', 600: '{teal.600}', 700: '{teal.700}', 800: '{teal.800}', 900: '{teal.900}', 950: '{teal.950}',
    },
  },
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(PrimeVue, { theme: { preset: Preset, options: { darkModeSelector: '.app-dark' } }, locale: ptBR })
app.use(ToastService)
app.use(ConfirmationService)
app.directive('tooltip', Tooltip)

const components = {
  Button, Card, Column, DataTable, Dialog, InputNumber, InputText, Message, MultiSelect, ProgressSpinner,
  Select, SelectButton, Skeleton, Tag, Textarea, ToggleSwitch, DatePicker, IconField, InputIcon,
}
Object.entries(components).forEach(([name, component]) => app.component(name, component))

app.mount('#app')
