#include "WatooMCombatCharacter.h"
#include "WatooMWanderComponent.h"
#include "WatooMAttributeSet.h"
#include "WatooMCombatData.h"
#include "WatooMCombatTags.h"
#include "WatooMAbilities.h"
#include "AbilitySystemComponent.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputActionValue.h"
#include "Engine/LocalPlayer.h"
#include "Kismet/GameplayStatics.h"
#include "Net/UnrealNetwork.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"

AWatooMCombatCharacter::AWatooMCombatCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bReplicates = true;
	AbilitySystem = CreateDefaultSubobject<UAbilitySystemComponent>(TEXT("AbilitySystem"));
	Wander = CreateDefaultSubobject<UWatooMWanderComponent>(TEXT("Wander"));
	AbilitySystem->SetIsReplicated(true);
	AbilitySystem->SetReplicationMode(EGameplayEffectReplicationMode::Mixed);
	Attributes = CreateDefaultSubobject<UWatooMAttributeSet>(TEXT("Attributes"));

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 350.f;
	CameraBoom->SocketOffset = FVector(0.f, 60.f, 70.f);
	CameraBoom->bUsePawnControlRotation = true;
	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false;
	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;

	WeaponStatic = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponStatic"));
	WeaponStatic->SetupAttachment(GetMesh());
	WeaponStatic->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	WeaponSkeletal = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("WeaponSkeletal"));
	WeaponSkeletal->SetupAttachment(GetMesh());
	WeaponSkeletal->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	MeleeAbility = UWatooMGA_Melee::StaticClass();
	GunAbility = UWatooMGA_Gun::StaticClass();
	ReloadAbility = UWatooMGA_Reload::StaticClass();
	SpellAbility = UWatooMGA_Spell::StaticClass();
}

void AWatooMCombatCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AWatooMCombatCharacter, Weapons);
	DOREPLIFETIME(AWatooMCombatCharacter, EquippedIndex);
	DOREPLIFETIME(AWatooMCombatCharacter, MagazineAmmo);
	DOREPLIFETIME(AWatooMCombatCharacter, ReserveAmmo);
	DOREPLIFETIME(AWatooMCombatCharacter, Spells);
}

void AWatooMCombatCharacter::BeginPlay()
{
	Super::BeginPlay();
	if (HasAuthority())
	{
		// Melee hits are swept along the weapon's bones on the server. By default a mesh only refreshes its bones while it is
		// rendered, and a server renders nothing (or not this pawn): the blade would freeze and every swing miss (T-0063).
		GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	}
	// Placed, unpossessed characters (target dummies, NPCs before possession) still get a working ability system.
	InitAbilitySystem();
	if (HasAuthority()) { GrantStartingAbilities(); }
}

void AWatooMCombatCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	InitAbilitySystem();
	GrantStartingAbilities();
}

void AWatooMCombatCharacter::OnRep_PlayerState()
{
	Super::OnRep_PlayerState();
	InitAbilitySystem();
}

void AWatooMCombatCharacter::InitAbilitySystem()
{
	AbilitySystem->InitAbilityActorInfo(this, this);
	if (bAbilitySystemReady) { return; }
	bAbilitySystemReady = true;
	AbilitySystem->GenericGameplayEventCallbacks.FindOrAdd(WatooMTags::Event_Hit.GetTag()).AddUObject(this, &AWatooMCombatCharacter::OnHitEvent);
	AbilitySystem->GenericGameplayEventCallbacks.FindOrAdd(WatooMTags::Event_Death.GetTag()).AddUObject(this, &AWatooMCombatCharacter::OnDeathEvent);
}

void AWatooMCombatCharacter::GrantStartingAbilities()
{
	if (!HasAuthority() || bAbilitiesGranted) { return; }
	bAbilitiesGranted = true;
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetTeamIdAttribute(), static_cast<float>(TeamId));
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetMaxHealthAttribute(), StartingMaxHealth);
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetHealthAttribute(), StartingMaxHealth);
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetMaxShieldAttribute(), StartingMaxShield);
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetShieldAttribute(), StartingShield);

	if (MeleeAbility) { AbilitySystem->GiveAbility(FGameplayAbilitySpec(MeleeAbility, 1, WatooMInput::Primary, this)); }
	if (GunAbility) { AbilitySystem->GiveAbility(FGameplayAbilitySpec(GunAbility, 1, WatooMInput::Primary, this)); }
	if (ReloadAbility) { AbilitySystem->GiveAbility(FGameplayAbilitySpec(ReloadAbility, 1, WatooMInput::Reload, this)); }
	for (UWatooMWeaponData* W : StartingWeapons) { if (W) { AddWeapon(W); } }
	for (UWatooMSpellData* S : StartingSpells) { if (S) { AddSpell(S); } }
	if (Weapons.Num() > 0 && EquippedIndex == INDEX_NONE) { EquipWeapon(0); }
}

void AWatooMCombatCharacter::GrantSpellAbility(UWatooMSpellData* Spell, int32 Slot)
{
	if (SpellAbility && Spell)
	{
		// One spec per spell: the spell data rides along as the spec's SourceObject.
		AbilitySystem->GiveAbility(FGameplayAbilitySpec(SpellAbility, 1, WatooMInput::SpellBase + Slot, Spell));
	}
}

UWatooMWeaponData* AWatooMCombatCharacter::GetEquippedWeapon() const
{
	return Weapons.IsValidIndex(EquippedIndex) ? Weapons[EquippedIndex].Get() : nullptr;
}

UMeshComponent* AWatooMCombatCharacter::GetWeaponMeshComponent() const
{
	const UWatooMWeaponData* W = GetEquippedWeapon();
	if (!W) { return nullptr; }
	return W->SkeletalMesh ? static_cast<UMeshComponent*>(WeaponSkeletal.Get()) : static_cast<UMeshComponent*>(WeaponStatic.Get());
}

bool AWatooMCombatCharacter::IsDead() const
{
	return AbilitySystem && AbilitySystem->HasMatchingGameplayTag(WatooMTags::State_Dead);
}

int32 AWatooMCombatCharacter::GetReserveAmmo() const
{
	return ReserveAmmo.IsValidIndex(EquippedIndex) ? ReserveAmmo[EquippedIndex] : 0;
}

int32 AWatooMCombatCharacter::AddWeapon(UWatooMWeaponData* Weapon)
{
	if (!HasAuthority() || !Weapon) { return INDEX_NONE; }
	const int32 Existing = Weapons.IndexOfByKey(Weapon);
	if (Existing != INDEX_NONE)
	{
		ReserveAmmo[Existing] += Weapon->MagazineSize;
		return Existing;
	}
	const int32 Slot = Weapons.Add(Weapon);
	const bool bGun = Weapon->UsesAmmo();
	MagazineAmmo.Add(bGun ? Weapon->MagazineSize : 0);
	ReserveAmmo.Add(bGun ? Weapon->StartingReserveAmmo : 0);
	return Slot;
}

void AWatooMCombatCharacter::AddSpell(UWatooMSpellData* Spell)
{
	if (!HasAuthority() || !Spell || Spells.Contains(Spell)) { return; }
	const int32 Slot = Spells.Add(Spell);
	GrantSpellAbility(Spell, Slot);
}

void AWatooMCombatCharacter::AddReserveAmmo(int32 Rounds)
{
	if (HasAuthority() && ReserveAmmo.IsValidIndex(EquippedIndex)) { ReserveAmmo[EquippedIndex] += FMath::Max(Rounds, 0); }
}

int32 AWatooMCombatCharacter::AddReserveAmmoFor(UWatooMWeaponData* Gun, int32 Rounds)
{
	if (!HasAuthority() || Rounds <= 0) { return 0; }
	int32 Slot = Gun ? Weapons.IndexOfByKey(Gun) : INDEX_NONE;
	if (!Gun)
	{
		const bool bEquippedGun = Weapons.IsValidIndex(EquippedIndex) && Weapons[EquippedIndex] && Weapons[EquippedIndex]->UsesAmmo();
		Slot = bEquippedGun ? EquippedIndex : Weapons.IndexOfByPredicate([](const UWatooMWeaponData* W) { return W && W->UsesAmmo(); });
	}
	if (!ReserveAmmo.IsValidIndex(Slot)) { return 0; }
	ReserveAmmo[Slot] += Rounds;
	return Rounds;
}

void AWatooMCombatCharacter::StoreMagazine()
{
	if (HasAuthority() && MagazineAmmo.IsValidIndex(EquippedIndex))
	{
		MagazineAmmo[EquippedIndex] = FMath::RoundToInt(AbilitySystem->GetNumericAttributeBase(UWatooMAttributeSet::GetAmmoAttribute()));
	}
}

void AWatooMCombatCharacter::LoadMagazine()
{
	if (!HasAuthority()) { return; }
	const UWatooMWeaponData* W = GetEquippedWeapon();
	const bool bGun = W && W->UsesAmmo();
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetMaxAmmoAttribute(), bGun ? W->MagazineSize : 0.f);
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetAmmoAttribute(),
		bGun && MagazineAmmo.IsValidIndex(EquippedIndex) ? MagazineAmmo[EquippedIndex] : 0.f);
}

int32 AWatooMCombatCharacter::ReloadEquipped()
{
	const UWatooMWeaponData* W = GetEquippedWeapon();
	if (!HasAuthority() || !W || !W->UsesAmmo()) { return 0; }
	const int32 InMag = FMath::RoundToInt(AbilitySystem->GetNumericAttributeBase(UWatooMAttributeSet::GetAmmoAttribute()));
	const int32 Moved = FMath::Min(W->MagazineSize - InMag, ReserveAmmo[EquippedIndex]);
	if (Moved <= 0) { return 0; }
	ReserveAmmo[EquippedIndex] -= Moved;
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetAmmoAttribute(), static_cast<float>(InMag + Moved));
	return Moved;
}

void AWatooMCombatCharacter::EquipWeapon(int32 Index)
{
	if (!HasAuthority()) { ServerEquipWeapon(Index); return; }
	if (!Weapons.IsValidIndex(Index) || Index == EquippedIndex) { return; }
	StoreMagazine();
	EquippedIndex = Index;
	LoadMagazine();
	ApplyEquippedMesh();
}

void AWatooMCombatCharacter::ServerEquipWeapon_Implementation(int32 Index) { EquipWeapon(Index); }

void AWatooMCombatCharacter::EquipNextWeapon()
{
	if (Weapons.Num() > 1) { EquipWeapon((EquippedIndex + 1) % Weapons.Num()); }
}

void AWatooMCombatCharacter::OnRep_Weapons() { ApplyEquippedMesh(); }

void AWatooMCombatCharacter::ApplyEquippedMesh()
{
	const UWatooMWeaponData* W = GetEquippedWeapon();
	WeaponStatic->SetStaticMesh(W ? W->StaticMesh.Get() : nullptr);
	WeaponSkeletal->SetSkeletalMesh(W ? W->SkeletalMesh.Get() : nullptr);
	WeaponStatic->SetVisibility(W && W->StaticMesh != nullptr);
	WeaponSkeletal->SetVisibility(W && W->SkeletalMesh != nullptr);
	if (W)
	{
		const FAttachmentTransformRules Rules(EAttachmentRule::SnapToTarget, true);
		UMeshComponent* Comp = GetWeaponMeshComponent();
		Comp->AttachToComponent(GetMesh(), Rules, W->AttachSocket);
		Comp->SetRelativeTransform(W->AttachOffset);
	}
}

void AWatooMCombatCharacter::ResetVitals()
{
	if (!HasAuthority()) { return; }
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetHealthAttribute(), AbilitySystem->GetNumericAttributeBase(UWatooMAttributeSet::GetMaxHealthAttribute()));
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetShieldAttribute(), StartingShield);
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetStaminaAttribute(), AbilitySystem->GetNumericAttributeBase(UWatooMAttributeSet::GetMaxStaminaAttribute()));
	AbilitySystem->SetNumericAttributeBase(UWatooMAttributeSet::GetManaAttribute(), AbilitySystem->GetNumericAttributeBase(UWatooMAttributeSet::GetMaxManaAttribute()));
	// Health > 0 through the attribute set also clears State.Dead; this covers a reset that never went through an effect.
	if (AbilitySystem->HasMatchingGameplayTag(WatooMTags::State_Dead))
	{
		AbilitySystem->RemoveLooseGameplayTag(WatooMTags::State_Dead, 1, EGameplayTagReplicationState::TagOnly);
	}
}

void AWatooMCombatCharacter::GetAim(FVector& OutStart, FVector& OutDirection) const
{
	OutStart = GetPawnViewLocation();
	OutDirection = GetBaseAimRotation().Vector();
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		FRotator R;
		PC->GetPlayerViewPoint(OutStart, R);
		OutDirection = R.Vector();
		// Start the trace at the character, not behind it at the camera, so nothing between camera and character is hit.
		OutStart += OutDirection * FVector::DotProduct(GetActorLocation() - OutStart, OutDirection);
	}
}

void AWatooMCombatCharacter::OnHitEvent(const FGameplayEventData* Payload)
{
	if (HasAuthority() && HitReactMontage && !IsDead()) { MulticastPlayMontage(HitReactMontage); }
}

void AWatooMCombatCharacter::OnDeathEvent(const FGameplayEventData* Payload)
{
	if (HasAuthority())
	{
		AbilitySystem->CancelAllAbilities();
		MulticastDeath();
	}
}

void AWatooMCombatCharacter::MulticastDeath_Implementation()
{
	GetCharacterMovement()->DisableMovement();
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	if (bRagdollOnDeath)
	{
		GetMesh()->SetCollisionProfileName(TEXT("Ragdoll"));
		GetMesh()->SetSimulatePhysics(true);
	}
	else if (DeathMontage)
	{
		PlayAnimMontage(DeathMontage);
	}
}

void AWatooMCombatCharacter::MulticastPlayMontage_Implementation(UAnimMontage* Montage)
{
	if (Montage) { PlayAnimMontage(Montage); }
}

void AWatooMCombatCharacter::MulticastPlayFx_Implementation(UNiagaraSystem* System, USoundBase* Sound, FVector_NetQuantize Location, FRotator Rotation, float Scale)
{
	if (System) { UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, System, Location, Rotation, FVector(Scale)); }
	if (Sound) { UGameplayStatics::PlaySoundAtLocation(this, Sound, Location); }
}

void AWatooMCombatCharacter::MulticastTracer_Implementation(UNiagaraSystem* System, FVector_NetQuantize Start, FVector_NetQuantize End)
{
	if (!System) { return; }
	if (UNiagaraComponent* C = UNiagaraFunctionLibrary::SpawnSystemAtLocation(this, System, Start, (End - Start).Rotation()))
	{
		C->SetVariableVec3(TEXT("User.BeamEnd"), End);   // unreal_niagara_fx.py tracer/beam recipes read User.BeamEnd
	}
}

void AWatooMCombatCharacter::PawnClientRestart()
{
	Super::PawnClientRestart();
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			if (DefaultMappingContext) { Sub->AddMappingContext(DefaultMappingContext, 0); }
		}
	}
}

void AWatooMCombatCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!EIC) { return; }
	if (MoveAction) { EIC->BindAction(MoveAction, ETriggerEvent::Triggered, this, &AWatooMCombatCharacter::Input_Move); }
	if (LookAction) { EIC->BindAction(LookAction, ETriggerEvent::Triggered, this, &AWatooMCombatCharacter::Input_Look); }
	if (JumpAction)
	{
		EIC->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
		EIC->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
	}
	if (NextWeaponAction) { EIC->BindAction(NextWeaponAction, ETriggerEvent::Started, this, &AWatooMCombatCharacter::EquipNextWeapon); }
	auto BindAbility = [this, EIC](UInputAction* Action, int32 Id)
	{
		if (!Action) { return; }
		EIC->BindAction(Action, ETriggerEvent::Started, this, &AWatooMCombatCharacter::Input_AbilityPressed, Id);
		EIC->BindAction(Action, ETriggerEvent::Completed, this, &AWatooMCombatCharacter::Input_AbilityReleased, Id);
	};
	BindAbility(PrimaryAction, WatooMInput::Primary);
	BindAbility(ReloadAction, WatooMInput::Reload);
	for (int32 i = 0; i < SpellActions.Num(); ++i) { BindAbility(SpellActions[i], WatooMInput::SpellBase + i); }
}

void AWatooMCombatCharacter::Input_Move(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	const FRotator Yaw(0.f, GetControlRotation().Yaw, 0.f);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), V.Y);
	AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), V.X);
}

void AWatooMCombatCharacter::Input_Look(const FInputActionValue& Value)
{
	const FVector2D V = Value.Get<FVector2D>();
	AddControllerYawInput(V.X);
	AddControllerPitchInput(V.Y);
}

void AWatooMCombatCharacter::Input_AbilityPressed(int32 InputId) { AbilitySystem->AbilityLocalInputPressed(InputId); }
void AWatooMCombatCharacter::Input_AbilityReleased(int32 InputId) { AbilitySystem->AbilityLocalInputReleased(InputId); }
