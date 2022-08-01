from datetime import date

from bootstrap_daterangepicker import widgets
from django.contrib.auth.models import Group, User
from django.contrib.postgres.fields import DateRangeField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives, send_mail
from django.utils.html import strip_tags
from .utils import CustomParser, EmailSender

# Create your models here.


class Huesped(models.Model):
    # attrs
    nombre = models.CharField(max_length=200)
    apellido = models.CharField(max_length=200)
    telefono = models.CharField(max_length=13)

    # punteros
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)

    # métodos

    def asignar_permiso(sender, instance, *args, **kwargs):
        group = Group.objects.get(name="huesped")
        instance.usuario.groups.add(group)

    def __str__(self) -> str:
        return f"{self.apellido.capitalize()}, {self.nombre.capitalize()}"

    class Meta:
        verbose_name_plural = "Huespedes"

    def get_absolute_url(self):
        return reverse("inquilinos:hue-det", kwargs={"pk": self.pk})


class Estado(models.Model):
    # attrs
    nombre = models.CharField(max_length=200)
    ambito = models.CharField(max_length=200)

    # métodos

    def esAmbitoCabaña(self, ambito) -> bool:
        if ambito == "cab":
            return True

    def esAmbitoReserva(self, ambito) -> bool:
        if ambito == "res":
            return True

    def __str__(self) -> str:
        if self.ambito == "cab":
            return f"{self.ambito.capitalize()}aña {self.nombre.capitalize()}"
        return f"{self.ambito.capitalize()}erva {self.nombre.capitalize()}"


class Cab(models.Model):
    # attrs
    nombre = models.CharField(
        max_length=200,
    )
    cantHabitaciones = models.IntegerField()
    costoPorNoche = models.FloatField(
        null=True,
    )
    slug = models.SlugField(null=False, blank=False, unique=True)

    # métodos
    def set_slug(sender, instance, *args, **kwargs):
        if instance.slug:
            return
        instance.slug = slugify(instance.nombre)

    def get_fechas_habilitadas(self):
        return CustomParser.parseRanges(ranges=self.rango_set.all())

    def get_fechas_deshabilitadas(self):
        return CustomParser.parseReservas(reservas=self.reserva_set.all())

    def get_fechas_hab_y_des(self):
        return (self.get_fechas_habilitadas, self.get_fechas_deshabilitadas)

    def crear_reserva(self, datos_reserva):
        nueva_reserva = Reserva(
            fechaDesde=datos_reserva["fechaDesde"],
            fechaHasta=datos_reserva["fechaHasta"],
            cantAdultos=datos_reserva["cantAdultos"],
            cantMenores=datos_reserva["cantMenores"],
            cab=self,
            huesped=datos_reserva["huesped"],
        )
        nueva_reserva.set_precio_final()
        nueva_reserva.save()
        nueva_reserva.set_estado("Pte Confirmacion")
        nueva_reserva.send_mail_enc_res()
        return nueva_reserva

    def __str__(self) -> str:
        return self.nombre

    class Meta:
        verbose_name = "Cabaña"
        verbose_name_plural = "Cabañas"
        ordering = [
            "-costoPorNoche",
            "-cantHabitaciones",
        ]


class Reserva(models.Model):
    # attrs
    fechaDesde = models.DateField()
    fechaHasta = models.DateField()
    fechaReserva = models.DateField(
        auto_now_add=True,
    )
    precioFinal = models.FloatField(
        null=True,
    )
    cantAdultos = models.PositiveSmallIntegerField(
        help_text="Cantidad de adultos",
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
    )
    cantMenores = models.PositiveSmallIntegerField(
        help_text="Cantidad de niños",
        validators=[
            MinValueValidator(0),
            MaxValueValidator(5),
        ],
        null=True,
    )

    # punteros
    huesped = models.ForeignKey(
        Huesped, on_delete=models.CASCADE, null=True, blank=True
    )

    cab = models.ForeignKey(Cab, on_delete=models.CASCADE, null=True)

    # estado = models.ForeignKey(Estado, on_delete=models.SET_NULL, null=True)

    # métodos

    def get_estado(self):
        instance = Reserva.objects.get(pk=self.pk)
        ultimo_cambio_estado = instance.cambioestado_set.get(fechaFin__isnull=True)
        return ultimo_cambio_estado.estado

    def get_cant_noches(self):
        return (self.fechaHasta - self.fechaDesde).days

    def calcular_precio_final(self):
        return self.get_cant_noches() * self.cab.costoPorNoche

    def set_precio_final(self):
        self.precioFinal = self.calcular_precio_final()

    def set_estado(self, nombre_estado):
        cambioEstado = CambioEstado(
            estado=Estado.objects.get(nombre=nombre_estado),
            reserva=self,
        )
        cambioEstado.save()

    def send_mail_enc_res(self):
        print("DESDE RESERVA: EmailSender.mail_reseerva(self, template_name)")
        EmailSender.mail_reserva(reserva=self, template_name="email_res_reg.html")

    def __str__(self) -> str:
        return f"{self.fechaDesde}->{self.fechaHasta}-{self.cab}"

    def get_precio_final(self) -> str:
        return f"$ {self.precioFinal}"

    class Meta:
        verbose_name_plural = "Reservas"
        permissions = (
            ("puede_registrar_reserva", "Este usuario puede registrar una reserva."),
        )


class Foto(models.Model):
    # attrs
    foto = models.ImageField(
        upload_to="cabs/",
    )
    descripcion = models.CharField(max_length=1000)
    # punteros
    cab = models.ForeignKey(Cab, on_delete=models.CASCADE, null=True)
    # métodos
    def __str__(self) -> str:
        return self.descripcion


class Rango(models.Model):
    # attrs
    fechaDesde = models.DateField()
    fechaHasta = models.DateField()
    # punteros
    cab = models.ForeignKey(Cab, on_delete=models.CASCADE, null=True)
    # métodos
    def __str__(self) -> str:
        return f"{self.fechaDesde}=>{self.fechaHasta}"


class Instalacion(models.Model):
    # attrs
    nombre = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=500)
    # punteros
    cab = models.ManyToManyField(Cab)
    # métodos
    def __str__(self) -> str:
        return f"{self.descripcion}"

    class Meta:
        verbose_name_plural = "Instalaciones"


class CambioEstado(models.Model):
    # attrs
    estado = models.ForeignKey(Estado, on_delete=models.CASCADE)
    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE)
    fechaFin = models.DateField(
        null=True,
    )
    fechaInicio = models.DateField(
        auto_now_add=True,
    )
